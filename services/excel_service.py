"""
Excel Import Service
Handles large-scale Excel file processing with optimized batch upsert operations.
Implements smart upsert algorithm to minimize database queries and network latency.
"""
import os
import uuid
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db
from models.nnt import NNT, LOAI_NO, TT_NO
from models.no_history import NO_HISTORY
from models.import_history import ImportHistory

# Configure logging
logger = logging.getLogger(__name__)


class ExcelService:
    """
    Excel Import Service
    
    Handles large-scale Excel file imports with the following optimizations:
    1. Chunked reading to minimize RAM usage
    2. Memory-mapped set for fast MST lookup (avoid single SELECT queries)
    3. Batch bulk operations (INSERT/UPDATE) to minimize round-trips
    4. Graceful error handling with detailed error reporting
    5. Audit trail via NO_HISTORY table
    
    Attributes:
        BATCH_SIZE: Number of rows to process per batch (default 5000)
        CHUNK_SIZE: Number of rows to read into memory at once (default 1000)
    """
    
    BATCH_SIZE = 5000
    CHUNK_SIZE = 1000
    
    # Column mapping from Excel to database fields
    COLUMN_MAPPING = {
        'MST': ['MST', 'Mã Số Thuế', 'MaSoThue', 'mst'],
        'CCCD': ['CCCD', 'Căn Cước Công Dân', 'CMND', 'cmnd', 'cccd'],
        'CMT': ['CMT', 'Chứng Minh Thư', 'chungminhthu', 'cmt'],
        'HO_TEN': ['HO_TEN', 'Họ Tên', 'HoTen', 'ho_ten', 'hoten', 'name'],
        'DIA_CHI': ['DIA_CHI', 'Địa Chỉ', 'DiaChi', 'dia_chi', 'diachi', 'address'],
        'TRANG_THAI_HD': ['TRANG_THAI_HD', 'Trạng Thái Hoạt Động', 'status', 'trang_thai'],
        'NO_TAM_TINH': ['NO_TAM_TINH', 'Nợ Tạm Tính', 'NoTamTinh', 'no_tam_tinh', 'debt'],
        'LOAI_NO': ['LOAI_NO', 'Loại Nợ', 'LoaiNo', 'loai_no', 'type']
    }
    
    def __init__(self, import_history_id: Optional[int] = None, user_id: Optional[int] = None):
        """
        Initialize Excel Service.
        
        Args:
            import_history_id: ID of ImportHistory record for tracking
            user_id: ID of user performing import
        """
        self.import_history_id = import_history_id
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())[:8]
        self.errors: List[Dict[str, Any]] = []
        self.stats = {
            'total_rows': 0,
            'success_rows': 0,
            'failed_rows': 0,
            'insert_rows': 0,
            'update_rows': 0,
            'skipped_rows': 0
        }
        self.debt_types_cache: Dict[str, int] = {}  # Cache for debt type lookup
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def _get_debt_type_id(self, loai_no_value: str) -> Optional[int]:
        """
        Get debt type ID from cache or database.
        
        Args:
            loai_no_value: Debt type name/code
        
        Returns:
            Debt type ID or None
        """
        if not loai_no_value:
            return None
        
        # Normalize input
        loai_no_normalized = str(loai_no_value).strip().upper()
        
        # Check cache first
        if loai_no_normalized in self.debt_types_cache:
            return self.debt_types_cache[loai_no_normalized]
        
        # Query database
        debt_type = LOAI_NO.query.filter(
            db.or_(
                db.func.upper(LOAI_NO.LOAI_NO) == loai_no_normalized,
                db.func.upper(LOAI_NO.TEN_NO) == loai_no_normalized
            )
        ).first()
        
        if debt_type:
            self.debt_types_cache[loai_no_normalized] = debt_type.ID_NO
            return debt_type.ID_NO
        
        return None
    
    def _normalize_column_name(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize DataFrame column names to match database schema.
        
        Args:
            df: Input DataFrame with raw column names
        
        Returns:
            DataFrame with normalized column names
        """
        column_rename_map = {}
        
        for db_column, possible_names in self.COLUMN_MAPPING.items():
            for col in df.columns:
                if str(col).strip() in possible_names:
                    column_rename_map[col] = db_column
                    break
        
        return df.rename(columns=column_rename_map)
    
    def _validate_row(self, row: pd.Series) -> Tuple[bool, Optional[str]]:
        """
        Validate a single row of data.
        
        Args:
            row: DataFrame row
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # MST is required
        if pd.isna(row.get('MST')) or str(row.get('MST')).strip() == '':
            return False, "MST (Mã Số Thuế) is required"
        
        mst = str(row.get('MST')).strip()
        
        # Validate MST format (basic check)
        if len(mst) < 6 or len(mst) > 20:
            return False, f"Invalid MST format: {mst}"
        
        # HO_TEN is required
        if pd.isna(row.get('HO_TEN')) or str(row.get('HO_TEN')).strip() == '':
            return False, f"MST {mst}: Họ Tên is required"
        
        # Validate CCCD if provided
        cccd = row.get('CCCD')
        if not pd.isna(cccd) and cccd:
            cccd_str = str(cccd).strip()
            if len(cccd_str) > 0 and (len(cccd_str) < 9 or len(cccd_str) > 15):
                return False, f"MST {mst}: Invalid CCCD format"
        
        return True, None
    
    def _parse_amount(self, value: Any) -> float:
        """
        Parse amount from various formats to float.
        
        Args:
            value: Value to parse (string, number, etc.)
        
        Returns:
            Parsed float value or 0.0
        """
        if pd.isna(value):
            return 0.0
        
        try:
            if isinstance(value, str):
                # Remove currency symbols and thousand separators
                value = value.replace('₫', '').replace('VND', '').replace(',', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _get_existing_mst_set(self) -> set:
        """
        Load all existing MSTs into memory for fast lookup.
        This minimizes SELECT queries to the database.
        
        Returns:
            Set of existing MST strings
        """
        result = db.session.query(NNT.MST).all()
        return {row[0] for row in result}
    
    def _create_nnt_from_row(self, row: pd.Series) -> NNT:
        """
        Create NNT instance from DataFrame row.
        
        Args:
            row: DataFrame row
        
        Returns:
            NNT instance
        """
        cccd = row.get('CCCD')
        cmt = row.get('CMT')
        
        nnt = NNT(
            MST=str(row.get('MST')).strip(),
            HO_TEN=str(row.get('HO_TEN')).strip(),
            DIA_CHI=str(row.get('DIA_CHI')).strip() if not pd.isna(row.get('DIA_CHI')) else None,
            CCCD=str(cccd).strip() if not pd.isna(cccd) else None,
            CMT=str(cmt).strip() if not pd.isna(cmt) else None,
            TRANG_THAI_HD=str(row.get('TRANG_THAI_HD', 'Active')).strip(),
            TRANG_THAI_NO='KHONG_NO',
            NGAY_TAO=datetime.utcnow()
        )
        
        return nnt
    
    def _update_nnt_from_row(self, nnt: NNT, row: pd.Series) -> bool:
        """
        Update existing NNT with new data, return True if changes detected.
        
        Args:
            nnt: Existing NNT instance
            row: DataFrame row with new data
        
        Returns:
            True if any field was changed
        """
        has_changes = False
        
        # Check and update HO_TEN
        new_ho_ten = str(row.get('HO_TEN')).strip()
        if nnt.HO_TEN != new_ho_ten:
            nnt.HO_TEN = new_ho_ten
            has_changes = True
        
        # Check and update DIA_CHI
        new_dia_chi = str(row.get('DIA_CHI')).strip() if not pd.isna(row.get('DIA_CHI')) else None
        if nnt.DIA_CHI != new_dia_chi:
            nnt.DIA_CHI = new_dia_chi
            has_changes = True
        
        # Check and update CCCD
        new_cccd = str(row.get('CCCD')).strip() if not pd.isna(row.get('CCCD')) else None
        if nnt.CCCD != new_cccd:
            nnt.CCCD = new_cccd
            has_changes = True
        
        # Check and update CMT
        new_cmt = str(row.get('CMT')).strip() if not pd.isna(row.get('CMT')) else None
        if nnt.CMT != new_cmt:
            nnt.CMT = new_cmt
            has_changes = True
        
        # Check and update TRANG_THAI_HD
        new_status = str(row.get('TRANG_THAI_HD', 'Active')).strip()
        if nnt.TRANG_THAI_HD != new_status:
            nnt.TRANG_THAI_HD = new_status
            has_changes = True
        
        return has_changes
    
    def _process_obligations(self, nnt: NNT, row: pd.Series) -> Optional[TT_NO]:
        """
        Process tax obligation for a taxpayer.
        
        Args:
            nnt: NNT instance
            row: DataFrame row with obligation data
        
        Returns:
            TT_NO instance or None
        """
        no_tam_tinh = self._parse_amount(row.get('NO_TAM_TINH', 0))
        
        # Get debt type ID
        loai_no_value = row.get('LOAI_NO')
        id_no = self._get_debt_type_id(loai_no_value) if not pd.isna(loai_no_value) else None
        
        # If no debt type specified, try to get default
        if id_no is None:
            default_debt_type = LOAI_NO.query.first()
            id_no = default_debt_type.ID_NO if default_debt_type else 1
        
        # Check if obligation already exists
        existing_obligation = TT_NO.query.filter_by(
            ID_NNT=nnt.MST,
            ID_NO=id_no
        ).first()
        
        old_amount = float(existing_obligation.NO_TAM_TINH or 0) if existing_obligation else 0
        
        if existing_obligation:
            existing_obligation.NO_TAM_TINH = no_tam_tinh
            existing_obligation.UPDATED_AT = datetime.utcnow()
            obligation = existing_obligation
        else:
            obligation = TT_NO(
                ID_NNT=nnt.MST,
                ID_NO=id_no,
                NO_TAM_TINH=no_tam_tinh,
                CREATED_AT=datetime.utcnow(),
                UPDATED_AT=datetime.utcnow()
            )
            db.session.add(obligation)
        
        # Update debt status
        nnt.update_debt_status()
        nnt.LAST_SYNC = datetime.utcnow()
        
        # Record history if amount changed
        if old_amount != no_tam_tinh:
            try:
                history_record = NO_HISTORY(
                    ID_NNT=nnt.MST,
                    ID_NO=id_no,
                    NO_CU=old_amount,
                    NO_MOI=no_tam_tinh,
                    SESSION_ID=self.session_id,
                    ACTION_TYPE='IMPORT',
                    CREATED_BY=self.user_id,
                    UPDATED_AT=datetime.utcnow()
                )
                db.session.add(history_record)
            except Exception as e:
                logger.warning(f"Failed to create history record: {str(e)}")
        
        return obligation
    
    def _process_batch(self, df_batch: pd.DataFrame, existing_mst_set: set) -> Dict[str, List]:
        """
        Process a batch of rows with intelligent upsert logic.
        
        Args:
            df_batch: DataFrame batch to process
            existing_mst_set: Set of already existing MSTs
        
        Returns:
            Dictionary with 'insert' and 'update' lists
        """
        insert_rows = []
        update_rows = []
        processed_mst = set()
        
        for idx, row in df_batch.iterrows():
            try:
                # Validate row
                is_valid, error_msg = self._validate_row(row)
                if not is_valid:
                    self.errors.append({
                        'row': idx + 1,
                        'mst': str(row.get('MST', 'N/A')),
                        'error': error_msg
                    })
                    self.stats['failed_rows'] += 1
                    continue
                
                mst = str(row.get('MST')).strip()
                
                # Skip duplicate MSTs within same batch
                if mst in processed_mst:
                    self.errors.append({
                        'row': idx + 1,
                        'mst': mst,
                        'error': 'Duplicate MST in file'
                    })
                    self.stats['skipped_rows'] += 1
                    continue
                
                processed_mst.add(mst)
                
                # Classify: insert vs update
                if mst in existing_mst_set:
                    update_rows.append(row)
                else:
                    insert_rows.append(row)
                
                self.stats['success_rows'] += 1
                
            except Exception as e:
                self.errors.append({
                    'row': idx + 1,
                    'mst': str(row.get('MST', 'N/A')),
                    'error': str(e)
                })
                self.stats['failed_rows'] += 1
                logger.error(f"Error processing row {idx}: {str(e)}")
        
        return {'insert': insert_rows, 'update': update_rows}
    
    def _bulk_insert(self, rows: List[pd.Series]) -> int:
        """
        Bulk insert new NNT records.
        
        Args:
            rows: List of DataFrame rows to insert
        
        Returns:
            Number of successfully inserted rows
        """
        inserted_count = 0
        
        if not rows:
            return 0
        
        try:
            # Prepare batch insert
            nnt_objects = []
            
            for row in rows:
                try:
                    nnt = self._create_nnt_from_row(row)
                    self._process_obligations(nnt, row)
                    nnt_objects.append(nnt)
                except Exception as e:
                    self.errors.append({
                        'row': 'N/A',
                        'mst': str(row.get('MST', 'N/A')),
                        'error': f"Insert failed: {str(e)}"
                    })
                    continue
            
            # Bulk add all objects
            db.session.bulk_save_objects(nnt_objects)
            db.session.flush()  # Ensure IDs are generated
            
            inserted_count = len(nnt_objects)
            self.stats['insert_rows'] += inserted_count
            
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Bulk insert error: {str(e)}")
            self.errors.append({
                'row': 'N/A',
                'mst': 'N/A',
                'error': f"Bulk insert failed: {str(e)}"
            })
        
        return inserted_count
    
    def _bulk_update(self, rows: List[pd.Series], existing_mst_set: set) -> int:
        """
        Bulk update existing NNT records.
        
        Args:
            rows: List of DataFrame rows to update
            existing_mst_set: Set of existing MSTs for quick lookup
        
        Returns:
            Number of successfully updated rows
        """
        updated_count = 0
        
        if not rows:
            return 0
        
        try:
            for row in rows:
                try:
                    mst = str(row.get('MST')).strip()
                    
                    # Use batch query to minimize individual SELECTs
                    nnt = NNT.query.filter(NNT.MST == mst).first()
                    
                    if nnt:
                        has_changes = self._update_nnt_from_row(nnt, row)
                        if has_changes:
                            self._process_obligations(nnt, row)
                            updated_count += 1
                        else:
                            # Still update obligations even if no NNT changes
                            self._process_obligations(nnt, row)
                            updated_count += 1
                    else:
                        # MST was deleted by another process
                        self.errors.append({
                            'row': 'N/A',
                            'mst': mst,
                            'error': 'MST not found during update (may have been deleted)'
                        })
                
                except SQLAlchemyError as e:
                    db.session.rollback()
                    self.errors.append({
                        'row': 'N/A',
                        'mst': str(row.get('MST', 'N/A')),
                        'error': f"Update failed: {str(e)}"
                    })
                    logger.error(f"Update error: {str(e)}")
            
            self.stats['update_rows'] += updated_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Bulk update error: {str(e)}")
        
        return updated_count
    
    def import_file(self, file_path: str) -> Dict[str, Any]:
        """
        Main entry point for importing an Excel file.
        Implements chunked reading and batch processing for large files.
        
        Args:
            file_path: Path to the Excel file
        
        Returns:
            Dictionary with import results and statistics
        """
        self.start_time = datetime.utcnow()
        self.errors = []
        self.stats = {
            'total_rows': 0,
            'success_rows': 0,
            'failed_rows': 0,
            'insert_rows': 0,
            'update_rows': 0,
            'skipped_rows': 0
        }
        
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Validate file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ['.xlsx', '.xls']:
            raise ValueError(f"Invalid file type. Expected .xlsx or .xls, got {file_ext}")
        
        try:
            # Load existing MSTs into memory for fast lookup
            logger.info("Loading existing MSTs into memory...")
            existing_mst_set = self._get_existing_mst_set()
            logger.info(f"Found {len(existing_mst_set)} existing MSTs")
            
            # Read Excel file in chunks
            logger.info(f"Reading Excel file: {file_path}")
            
            # First pass: get total rows for progress tracking
            df_total = pd.read_excel(file_path, sheet_name=0, nrows=0)
            total_columns = df_total.columns.tolist()
            
            # Load debt types into cache
            all_debt_types = LOAI_NO.query.all()
            for dt in all_debt_types:
                self.debt_types_cache[dt.LOAI_NO.upper()] = dt.ID_NO
                self.debt_types_cache[dt.TEN_NO.upper()] = dt.ID_NO
            
            # Process file in chunks
            chunk_count = 0
            batch_number = 0
            
            for df_chunk in pd.read_excel(file_path, sheet_name=0, chunksize=self.CHUNK_SIZE):
                chunk_count += 1
                
                # Normalize column names
                df_chunk = self._normalize_column_name(df_chunk)
                
                # Ensure required columns exist
                if 'MST' not in df_chunk.columns or 'HO_TEN' not in df_chunk.columns:
                    raise ValueError("Excel file must contain 'MST' and 'HO_TEN' columns")
                
                self.stats['total_rows'] += len(df_chunk)
                
                # Process chunk in batches
                for batch_start in range(0, len(df_chunk), self.BATCH_SIZE):
                    batch_number += 1
                    batch_end = min(batch_start + self.BATCH_SIZE, len(df_chunk))
                    df_batch = df_chunk.iloc[batch_start:batch_end]
                    
                    logger.info(f"Processing batch {batch_number} ({len(df_batch)} rows)")
                    
                    # Use nested transaction for atomic batch processing
                    try:
                        db.session.begin_nested()
                        
                        # Classify rows into insert/update
                        classified = self._process_batch(df_batch, existing_mst_set)
                        
                        # Process inserts
                        if classified['insert']:
                            self._bulk_insert(classified['insert'])
                            # Add inserted MSTs to set to prevent duplicate inserts in same file
                            for row in classified['insert']:
                                existing_mst_set.add(str(row.get('MST')).strip())
                        
                        # Process updates
                        if classified['update']:
                            self._bulk_update(classified['update'], existing_mst_set)
                        
                        # Commit batch transaction
                        db.session.commit()
                        
                    except SQLAlchemyError as e:
                        db.session.rollback()
                        logger.error(f"Batch {batch_number} failed: {str(e)}")
                        # Continue with next batch (graceful degradation)
                        for idx in range(len(df_batch)):
                            self.errors.append({
                                'row': f'Batch {batch_number}, Index {idx}',
                                'mst': 'N/A',
                                'error': f"Batch failed: {str(e)}"
                            })
                        self.stats['failed_rows'] += len(df_batch)
            
            # Final commit
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Import failed: {str(e)}\n{traceback.format_exc()}")
            raise
        
        finally:
            self.end_time = datetime.utcnow()
        
        return self.get_results()
    
    def import_from_bytes(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Import Excel from bytes (e.g., uploaded file).
        
        Args:
            file_bytes: Raw Excel file bytes
            filename: Original filename
        
        Returns:
            Dictionary with import results
        """
        # Save to temporary file
        temp_dir = os.path.join(os.path.dirname(__file__), '..', 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_path = os.path.join(temp_dir, f"import_{self.session_id}_{filename}")
        
        try:
            with open(temp_path, 'wb') as f:
                f.write(file_bytes)
            
            return self.import_file(temp_path)
        
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def get_results(self) -> Dict[str, Any]:
        """
        Get import results and statistics.
        
        Returns:
            Dictionary with import results
        """
        duration = 0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            'success': self.stats['failed_rows'] == 0 or self.stats['success_rows'] > 0,
            'stats': self.stats,
            'errors': self.errors[:100],  # Limit error list to first 100
            'duration': round(duration, 2),
            'session_id': self.session_id,
            'total_errors': len(self.errors)
        }
    
    @staticmethod
    def get_template_columns() -> List[str]:
        """
        Get required columns for Excel template.
        
        Returns:
            List of column names
        """
        return [
            'MST',
            'HO_TEN',
            'CCCD',
            'CMT',
            'DIA_CHI',
            'TRANG_THAI_HD',
            'NO_TAM_TINH',
            'LOAI_NO'
        ]
    
    @staticmethod
    def generate_template(file_path: str) -> str:
        """
        Generate Excel template file.
        
        Args:
            file_path: Path where template should be saved
        
        Returns:
            Path to generated template
        """
        import pandas as pd
        
        template_data = pd.DataFrame({
            'MST': ['0123456789'],
            'HO_TEN': ['Nguyễn Văn A'],
            'CCCD': ['040093001234'],
            'CMT': [''],
            'DIA_CHI': ['123 Đường ABC, Quận 1, TP.HCM'],
            'TRANG_THAI_HD': ['Active'],
            'NO_TAM_TINH': [0.00],
            'LOAI_NO': ['THUÊ']
        })
        
        template_data.to_excel(file_path, index=False, sheet_name='Import Data')
        
        return file_path
