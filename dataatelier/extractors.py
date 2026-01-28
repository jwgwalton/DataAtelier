"""Text extraction utilities for DataAtelier."""

import json
import xml.etree.ElementTree as ET
from typing import Optional
import chardet
from io import BytesIO


def robust_decode(data: bytes, fallback_encoding: str = 'utf-8', errors: str = 'replace') -> str:
    """Robustly decode bytes to string using chardet for encoding detection.
    
    Args:
        data: Bytes to decode
        fallback_encoding: Encoding to use if detection fails
        errors: How to handle decoding errors ('strict', 'ignore', 'replace')
        
    Returns:
        Decoded string
    """
    if not data:
        return ""
    
    # Try chardet detection
    try:
        detection = chardet.detect(data)
        encoding = detection.get('encoding')
        confidence = detection.get('confidence', 0)
        
        # Use detected encoding if confidence is reasonable
        if encoding and confidence > 0.7:
            return data.decode(encoding, errors=errors)
    except Exception:
        pass
    
    # Fall back to specified encoding
    try:
        return data.decode(fallback_encoding, errors=errors)
    except Exception:
        # Last resort: latin-1 always works
        return data.decode('latin-1', errors=errors)


def extract_text_from_txt(content: bytes, max_bytes: int) -> str:
    """Extract text from plain text files.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process
        
    Returns:
        Extracted text
    """
    data = content[:max_bytes] if max_bytes > 0 else content
    return robust_decode(data)


def extract_text_from_json(content: bytes, max_bytes: int) -> str:
    """Extract text from JSON files.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process
        
    Returns:
        Formatted JSON as string
    """
    data = content[:max_bytes] if max_bytes > 0 else content
    text = robust_decode(data)
    
    try:
        # Parse and pretty-print JSON for better readability
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        # Return raw text if JSON parsing fails
        return text


def extract_text_from_xml(content: bytes, max_bytes: int) -> str:
    """Extract text from XML files.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process
        
    Returns:
        Extracted text from XML
    """
    data = content[:max_bytes] if max_bytes > 0 else content
    text = robust_decode(data)
    
    try:
        # Parse XML and extract all text content
        root = ET.fromstring(text)
        texts = [elem.text for elem in root.iter() if elem.text and elem.text.strip()]
        return "\n".join(texts)
    except ET.ParseError:
        # Return raw text if XML parsing fails
        return text


def extract_text_from_csv(content: bytes, max_bytes: int) -> str:
    """Extract text from CSV files.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process
        
    Returns:
        CSV content as text
    """
    data = content[:max_bytes] if max_bytes > 0 else content
    return robust_decode(data)


def extract_text_from_pdf(content: bytes, max_bytes: int) -> str:
    """Extract text from PDF files using pdfminer.six.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process (for preview, not PDF parsing)
        
    Returns:
        Extracted text from PDF
    """
    try:
        from pdfminer.high_level import extract_text as pdf_extract_text
        
        # PDF parsing needs the full content, but we'll truncate the result
        pdf_file = BytesIO(content)
        text = pdf_extract_text(pdf_file)
        
        # Truncate to approximate character limit based on max_bytes
        if max_bytes > 0:
            # Rough approximation: 1 byte ≈ 1 character
            text = text[:max_bytes]
            
        return text.strip()
        
    except ImportError:
        return "[PDF extraction unavailable - pdfminer.six not installed]"
    except Exception as e:
        return f"[PDF extraction failed: {str(e)}]"


def extract_text_from_docx(content: bytes, max_bytes: int) -> str:
    """Extract text from DOCX files using python-docx.
    
    Args:
        content: File content as bytes
        max_bytes: Maximum bytes to process (for preview, not DOCX parsing)
        
    Returns:
        Extracted text from DOCX
    """
    try:
        from docx import Document
        
        # DOCX parsing needs the full content
        docx_file = BytesIO(content)
        doc = Document(docx_file)
        
        # Extract all paragraphs
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        text = "\n".join(paragraphs)
        
        # Truncate to approximate character limit based on max_bytes
        if max_bytes > 0:
            text = text[:max_bytes]
            
        return text.strip()
        
    except ImportError:
        return "[DOCX extraction unavailable - python-docx not installed]"
    except Exception as e:
        return f"[DOCX extraction failed: {str(e)}]"


def extract_text_preview(
    content: bytes, 
    content_type: str, 
    max_bytes: int
) -> str:
    """Extract text preview from various file types.
    
    Args:
        content: File content as bytes
        content_type: MIME type or file extension
        max_bytes: Maximum bytes to extract for preview
        
    Returns:
        Extracted text preview
    """
    if not content:
        return ""
    
    # Normalize content type
    content_type_lower = content_type.lower()
    
    # Map content types to extractors
    if any(t in content_type_lower for t in ['text/plain', '.txt', 'text/']):
        return extract_text_from_txt(content, max_bytes)
    
    elif any(t in content_type_lower for t in ['application/json', '.json', 'json']):
        return extract_text_from_json(content, max_bytes)
    
    elif any(t in content_type_lower for t in ['application/xml', 'text/xml', '.xml', 'xml']):
        return extract_text_from_xml(content, max_bytes)
    
    elif any(t in content_type_lower for t in ['text/csv', '.csv', 'csv']):
        return extract_text_from_csv(content, max_bytes)
    
    elif any(t in content_type_lower for t in ['application/pdf', '.pdf', 'pdf']):
        return extract_text_from_pdf(content, max_bytes)
    
    elif any(t in content_type_lower for t in [
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.docx',
        'docx'
    ]):
        return extract_text_from_docx(content, max_bytes)
    
    else:
        # For unknown types, try robust text extraction
        data = content[:max_bytes] if max_bytes > 0 else content
        return robust_decode(data)
