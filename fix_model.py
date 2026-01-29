"""
Quick Fix Script - Add extend_existing=True to all models
Run this script to automatically fix all your model files
"""

import os
import re

# List of all model files
MODEL_FILES = [
    "user.py",
    "business.py",
    "customer.py",
    "product.py",
    "invoice.py",
    "invoice_item.py",
    "payment.py",
    "document.py",
    "document_item.py",
    "vat_period.py",
    "ai_insight.py",
    "audit_log.py",
    "notification_preference.py",
]

def fix_model_file(filepath):
    """Add extend_existing=True to a model file if not present"""
    
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already has extend_existing
    if 'extend_existing' in content:
        print(f"✓ Already fixed: {filepath}")
        return True
    
    # Pattern to find __tablename__ = "something"
    pattern = r'(__tablename__\s*=\s*["\'][^"\']+["\'])'
    
    # Replacement with __table_args__ added
    replacement = r'\1\n    __table_args__ = {\'extend_existing\': True}'
    
    # Apply the fix
    new_content = re.sub(pattern, replacement, content, count=1)
    
    if new_content != content:
        # Backup original file
        backup_path = filepath + '.backup'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Write fixed content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✓ Fixed: {filepath} (backup: {backup_path})")
        return True
    else:
        print(f"⚠️  Could not fix: {filepath}")
        return False

def main():
    """Fix all model files"""
    print("=" * 70)
    print("SQLAlchemy Models Quick Fix Script")
    print("=" * 70)
    print()
    
    # Get the models directory path
    models_dir = os.path.join("app", "models")
    
    if not os.path.exists(models_dir):
        print(f"❌ Models directory not found: {models_dir}")
        print("   Make sure you're running this from the project root directory")
        return
    
    print(f"Models directory: {models_dir}")
    print()
    
    fixed_count = 0
    for model_file in MODEL_FILES:
        filepath = os.path.join(models_dir, model_file)
        if fix_model_file(filepath):
            fixed_count += 1
    
    print()
    print("=" * 70)
    print(f"Fixed {fixed_count} out of {len(MODEL_FILES)} model files")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review the changes in your model files")
    print("2. Run: uvicorn app.main:app --reload")
    print("3. If something breaks, restore from .backup files")

if __name__ == "__main__":
    main()