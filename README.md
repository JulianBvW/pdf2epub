# :page_facing_up: pdf2epub :open_book:

_CLI tool for converting a PDF to an EPUB file._

---

- Do you want to read a book on your phone but only have the pdf which **doesn't scale well**?
- Or maybe the book is **just available** as PDF and not as EPUB?

-> Use this script to convert the PDF to an EPUB which you can then import into your favorite reader.

## Usage

Download the `pdf2epub.py` script and run it:

```bash
python pdf2epub.py <path/to/file.pdf> <title> <author> [flags]
```

The output will be saved as `path/to/file.epub`.

### Example

```bash
python pdf2epub.py ./hp5.pdf Harry\ Potter\ 5 JK\ Rowling -f 7 -p 7 -r -\ [0-9]+\ -
```

### Flags

Flag | Shortcut | Default | Function
--- | :-: | :-: | ---
`--cover N`               | `-c` | 1        | The page of the cover image*.
`--first N`               | `-f` | 2        | The first page containing the content.
`--image_scale N`         | `-s` | 4        | Multiplier for image resolution.
`--language LANG`         | `-l` | 'de'     | Configure eBook language setting.
`--pagenumberstart N`     | `-p` | 0        | The page where numbering startes (0 if no numbering).
`--pagenumberredex REDEX` | `-r` | '[0-9]+' | The REDEX to match the numbering against.


*If you want to use your own image, set this to 0 and paste the image into './tmp/img-cover.jpeg'.

## Requirements

Requirement | Version
--- | ---
Python | 3
ebooklib | 0.17.1+
pymupdf | 1.20.1+