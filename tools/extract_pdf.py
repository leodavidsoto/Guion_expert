#!/usr/bin/env python3
import sys
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF"""
    try:
        import PyPDF2
        
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n\n"
            return text
    except ImportError:
        # Fallback: usar pdftotext si está disponible
        import subprocess
        result = subprocess.run(
            ['pdftotext', pdf_path, '-'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return "Error: No se pudo extraer texto del PDF"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python3 extract_pdf.py archivo.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    text = extract_text_from_pdf(pdf_path)
    print(text)
