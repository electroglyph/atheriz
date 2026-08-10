import re

def extract_unique_chars(input_filename, output_filename):
    try:
        # Try UTF-8 first (modern exports often use this for Unicode block chars)
        with open(input_filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {input_filename} not found.")
        return
    except UnicodeDecodeError:
        # Fallback to standard DOS codepage for classic ANSI files
        with open(input_filename, 'r', encoding='cp437') as f:
            content = f.read()

    # Strip ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_content = ansi_escape.sub('', content)

    # Get unique characters
    unique_chars = set(clean_content)

    # Filter into categories for easier reading
    ascii_chars = sorted([c for c in unique_chars if ord(c) < 128 and not c.isspace()])
    unicode_chars = sorted([c for c in unique_chars if ord(c) >= 128])

    with open(output_filename, 'w', encoding='utf-8') as out_f:
        out_f.write("=== Unique ASCII Characters ===\n")
        out_f.write(''.join(ascii_chars) + "\n\n")
        
        out_f.write("=== Unique Unicode Characters ===\n")
        # Added spaces between unicode characters for better readability
        out_f.write(' '.join(unicode_chars) + "\n\n")
        
        out_f.write("=== Python String Representation ===\n")
        out_f.write(repr(''.join(sorted(list(unique_chars)))) + "\n")

    print(f"Extracted characters have been saved to '{output_filename}'")

if __name__ == "__main__":
    extract_unique_chars("art.ans", "unique_chars.txt")
