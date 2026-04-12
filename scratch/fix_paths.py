import os
import glob

PATH_FIX = """import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

"""

folders = [
    'scripts/diagnostics',
    'scripts/tools'
]

def update_folder(folder):
    pattern = os.path.join(folder, '*.py')
    files = glob.glob(pattern)
    print(f"Updating folder: {folder} ({len(files)} files)")
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if fix already exists
            if 'sys.path.append' in content and 'dirname(__file__)' in content:
                print(f"  Skipping (already fixed): {fpath}")
                continue
            
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(PATH_FIX + content)
            print(f"  Updated: {fpath}")
        except Exception as e:
            print(f"  Error updating {fpath}: {e}")

if __name__ == "__main__":
    for folder in folders:
        update_folder(folder)
