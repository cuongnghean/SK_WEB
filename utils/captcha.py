"""
Captcha Generator and Validator
Provides custom captcha generation for public search protection.
"""
import os
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
from io import BytesIO

from flask import session, request, jsonify, make_response
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class CaptchaGenerator:
    """
    Captcha Generator
    
    Generates and validates image captchas for form protection.
    Features:
    - Random text generation with configurable length
    - Multiple font sizes and positions
    - Background noise and distortion
    - Session-based validation
    - Time-limited validity
    
    Usage:
        generator = CaptchaGenerator()
        image_data, code = generator.generate()
        # Display image and get user input
        is_valid = generator.validate(user_input)
    """
    
    # Captcha session key
    SESSION_KEY = 'captcha_code'
    EXPIRY_KEY = 'captcha_expiry'
    
    # Default configuration
    DEFAULT_LENGTH = 4
    DEFAULT_EXPIRY = 300  # 5 minutes
    
    # Character sets
    CHAR_SET = string.ascii_uppercase + string.digits
    EXCLUDE_CHARS = 'O0I1L'  # Characters that look similar
    
    def __init__(self, length: int = None, expiry: int = None):
        """
        Initialize Captcha Generator.
        
        Args:
            length: Number of characters in captcha (default: 4)
            expiry: Validity period in seconds (default: 300)
        """
        from flask import current_app
        
        self.length = length or getattr(current_app.config, 'CAPTCHA_LENGTH', self.DEFAULT_LENGTH)
        self.expiry = expiry or getattr(current_app.config, 'CAPTCHA_EXPIRY', self.DEFAULT_EXPIRY)
        
        # Image configuration
        self.width = 120
        self.height = 40
        self.bg_color = (255, 255, 255)  # White background
        self.text_color = (0, 0, 0)       # Black text
        self.noise_color = (200, 200, 200)  # Light gray noise
        
        # Try to use a system font, fallback to default
        self.font_size = 24
    
    def _get_char_set(self) -> str:
        """
        Get character set for captcha generation.
        Excludes ambiguous characters.
        
        Returns:
            Filtered character set string
        """
        return ''.join(c for c in self.CHAR_SET if c not in self.EXCLUDE_CHARS)
    
    def _generate_code(self) -> str:
        """
        Generate random captcha code.
        
        Returns:
            Random string of characters
        """
        char_set = self._get_char_set()
        return ''.join(random.choices(char_set, k=self.length))
    
    def _get_font(self) -> ImageFont.FreeTypeFont:
        """
        Get font for captcha text.
        Tries multiple font options for compatibility.
        
        Returns:
            PIL ImageFont object
        """
        try:
            # Try common system fonts
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                'C:\\Windows\\Fonts\\arial.ttf',
                'C:\\Windows\\Fonts\\verdana.ttf',
                '/System/Library/Fonts/Helvetica.ttc',
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, self.font_size)
            
            # Fallback to default
            return ImageFont.load_default()
            
        except Exception as e:
            logger.warning(f"Could not load custom font: {e}")
            return ImageFont.load_default()
    
    def _draw_noise(self, image: Image.Image) -> None:
        """
        Add random noise lines to the image.
        
        Args:
            image: PIL Image object
        """
        draw = ImageDraw.Draw(image)
        width, height = image.size
        
        # Add random lines
        for _ in range(random.randint(3, 6)):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            draw.line([(x1, y1), (x2, y2)], fill=self.noise_color, width=1)
        
        # Add random circles/dots
        for _ in range(random.randint(5, 10)):
            x = random.randint(0, width)
            y = random.randint(0, height)
            r = random.randint(1, 2)
            draw.ellipse([x-r, y-r, x+r, y+r], fill=self.noise_color)
    
    def _warp_text(self, image: Image.Image) -> Image.Image:
        """
        Apply simple distortion to the image.
        
        Args:
            image: Original PIL Image
        
        Returns:
            Distorted PIL Image
        """
        # Simple implementation - can be enhanced with more distortion
        return image
    
    def generate(self) -> Tuple[bytes, str]:
        """
        Generate a new captcha image and code.
        
        Returns:
            Tuple of (image_bytes, captcha_code)
        """
        # Generate random code
        code = self._generate_code()
        
        # Create image
        image = Image.new('RGB', (self.width, self.height), color=self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # Get font
        font = self._get_font()
        
        # Calculate text position
        text_width = sum(font.getbbox(c)[2] for c in code)
        text_height = font.getbbox('A')[3] - font.getbbox('A')[1]
        x_offset = (self.width - text_width) // 2
        y_offset = (self.height - text_height) // 2
        
        # Draw each character with slight variation
        x_pos = x_offset
        for char in code:
            # Add slight rotation effect by drawing at different y positions
            y_offset_char = y_offset + random.randint(-3, 3)
            draw.text((x_pos, y_offset_char), char, fill=self.text_color, font=font)
            char_width = font.getbbox(char)[2]
            x_pos += char_width + random.randint(2, 5)
        
        # Add noise
        self._draw_noise(image)
        
        # Convert to bytes
        image_bytes = BytesIO()
        image.save(image_bytes, format='PNG')
        image_bytes = image_bytes.getvalue()
        
        # Store in session
        expiry_time = datetime.utcnow() + timedelta(seconds=self.expiry)
        session[CaptchaGenerator.SESSION_KEY] = code.upper()
        session[CaptchaGenerator.EXPIRY_KEY] = expiry_time.isoformat()
        
        return image_bytes, code
    
    def generate_response(self) -> Tuple[bytes, str]:
        """
        Generate captcha and return as HTTP response.
        
        Returns:
            Tuple of (image_bytes, captcha_code)
        """
        return self.generate()
    
    def get_image_response(self) -> Any:
        """
        Generate captcha and return as Flask response.
        
        Returns:
            Flask response with PNG image
        """
        image_bytes, code = self.generate()
        
        response = make_response(image_bytes)
        response.headers['Content-Type'] = 'image/png'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    
    @staticmethod
    def validate(user_input: str) -> bool:
        """
        Validate user captcha input against stored session value.
        
        Args:
            user_input: User's captcha input
        
        Returns:
            True if valid and not expired
        """
        try:
            stored_code = session.get(CaptchaGenerator.SESSION_KEY)
            expiry_str = session.get(CaptchaGenerator.EXPIRY_KEY)
            
            if not stored_code or not expiry_str:
                return False
            
            # Check expiry
            expiry_time = datetime.fromisoformat(expiry_str)
            if datetime.utcnow() > expiry_time:
                CaptchaGenerator.clear()
                return False
            
            # Check code match (case insensitive)
            if not user_input:
                return False
            
            is_valid = user_input.strip().upper() == stored_code
            
            # Clear after successful validation to prevent replay
            if is_valid:
                CaptchaGenerator.clear()
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Captcha validation error: {str(e)}")
            return False
    
    @staticmethod
    def clear() -> None:
        """Clear captcha session data."""
        session.pop(CaptchaGenerator.SESSION_KEY, None)
        session.pop(CaptchaGenerator.EXPIRY_KEY, None)
    
    @staticmethod
    def get_stored_code() -> Optional[str]:
        """
        Get stored captcha code (for debugging only).
        
        Returns:
            Stored captcha code or None
        """
        return session.get(CaptchaGenerator.SESSION_KEY)


def validate_captcha(user_input: str) -> Tuple[bool, Optional[str]]:
    """
    Validate captcha input and return detailed result.
    
    Args:
        user_input: User's captcha input
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not user_input:
        return False, "Vui lòng nhập mã xác thực"
    
    if len(user_input) < 4:
        return False, "Mã xác thực không đúng"
    
    if CaptchaGenerator.validate(user_input):
        return True, None
    
    return False, "Mã xác thực không hợp lệ hoặc đã hết hạn"


def require_captcha(f):
    """
    Decorator to require valid captcha for a route.
    
    Args:
        f: Function to decorate
    
    Returns:
        Decorated function
    """
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, jsonify
        
        # Check for captcha in request
        captcha_input = None
        
        if request.is_json:
            data = request.get_json()
            captcha_input = data.get('captcha') if data else None
        else:
            captcha_input = request.form.get('captcha')
        
        if not captcha_input:
            return jsonify({
                'success': False,
                'error': 'Captcha required',
                'message': 'Vui lòng nhập mã xác thực'
            }), 400
        
        is_valid, error_msg = validate_captcha(captcha_input)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': 'Invalid captcha',
                'message': error_msg
            }), 400
        
        return f(*args, **kwargs)
    
    return decorated_function
