import fitz
from ebooklib import epub

import argparse

import random
import re
import os
if not os.path.exists('tmp'):
    os.mkdir('tmp')

parser = argparse.ArgumentParser(description='Create an EPUB file from a PDF.')

parser.add_argument('file', type=str, help='the PDF file you want to convert')
parser.add_argument('title', type=str, help='the title of the book')
parser.add_argument('author', type=str, help='the name of the author')

parser.add_argument('-c', '--cover', type=int, default=1, metavar='N', help='the page of the cover image (0 if none -> paste img-cover.jpeg to ./tmp/), default=1')
parser.add_argument('-f', '--first', type=int, default=2, metavar='N', help='the first page containing actual text to convert, default=2')
parser.add_argument('-s', '--image_scale', type=int, default=4, metavar='N', help='the multiplier for image resolution, default=4')
parser.add_argument('-l', '--language', type=str, default='de', metavar='', help='the specified language, default=de')
parser.add_argument('-p', '--pagenumberstart', type=int, default=0, metavar='', help='the page where page numbers start (0 if none), default=-1')
parser.add_argument('-r', '--pagenumberredex', type=str, default='[0-9]+', metavar='', help='the redex to match page numbering against, default=\'[0-9]+\'')

args = parser.parse_args()

print(f'Converting {args.file} to ebook with:')
print(f'- Title:              {args.title}')
print(f'- Author:             {args.author}')
print(f'- First Page:         {args.first}')
print(f'- Image Scale:        {args.image_scale}')
print(f'- Language:           {args.language}')
print(f'- Pagenumber Start:   {args.pagenumberstart}')
print(f'- Pagenumber Redex:   {args.pagenumberredex}')

UNCERTAINTY_END = 10
UNCERTAINTY_SIZE = 2
UNCERTAINTY_LINE_HEIGTH = 2

HTML_CHARS = [('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;')]

#######################
#--> Functions

### Helper

def get_flags(flags):
    '''Make font flags human readable.'''
    l = []
    if flags & 2 ** 0:
        l.append('superscript')
    if flags & 2 ** 1:
        l.append('italic')
    if flags & 2 ** 2:
        l.append('serifed')
    else:
        l.append('sans')
    if flags & 2 ** 3:
        l.append('monospaced')
    else:
        l.append('proportional')
    if flags & 2 ** 4:
        l.append('bold')
    return l

def htmlify(text):
    for (pat, sub) in HTML_CHARS:
        text = re.sub(pat, sub, text)
    return text

def same(a, b, uncertainty):
    return a <= b + uncertainty and a >= b - uncertainty

### Save Image

def save_image(page, bbox, img_nr):
    page.get_pixmap(matrix=fitz.Matrix(args.image_scale, args.image_scale), clip=bbox).pil_save(f'tmp/img-{img_nr}.jpeg')

### Extract Content

def get_spans(book, starting_page=1, pagenumber_start=0, pagenumberredex='[0-9]+'):
    spans = []
    img_nr = 0
    for page_nr in range(starting_page-1, book.page_count):
        blocks = book[page_nr].get_text('dict')['blocks']
        for block in blocks:

            # Handle TEXT Blocks
            if block['type'] == 0:

                # Remove the page number if needed
                if pagenumber_start > 0 and page_nr >= pagenumber_start-1 and len(block['lines']) == 1 and len(block['lines'][0]['spans']) == 1 and bool(re.match(pagenumberredex, block['lines'][0]['spans'][0]['text'].strip())):
                   continue

                # Flatten all Spans in all Lines
                for line in block['lines']:
                    for span in line['spans']:
                        if span['text'].strip() != '':
                            spans.append({
                                'text': htmlify(span['text']),
                                'size': round(span['size']),
                                'y_org': round(span['origin'][1]),
                                'x_end': round(span['bbox'][2]),
                                'flags': span['flags']
                            })

            # Handle IMAGE Blocks
            if block['type'] == 1:
                save_image(book[page_nr], block['bbox'], img_nr)
                spans.append({
                    'text': f'<img width="90%" src="img-{img_nr}.jpeg"/>',
                    'size': -1, 'y_org': -1, 'x_end': -1, 'flags': -1
                })
                img_nr += 1

    return spans

def group_spans_in_lines(spans):
    lines = []
    current_line_y = spans[0]['y_org']
    current_span_list = []
    for span in spans:
        if same(span['y_org'], current_line_y, UNCERTAINTY_LINE_HEIGTH):
            current_span_list.append(span)
        else:
            lines.append(current_span_list)
            current_line_y = span['y_org']
            current_span_list = [span]
    lines.append(current_span_list)
    return lines

def get_text_constants(lines):
    text_sizes = {}
    text_ends = {}
    for line in lines:

        span = line[-1]
        text_len, text_size, text_end = len(span['text']), span['size'], span['x_end']

        if not (text_size in text_sizes):
            text_sizes[text_size] = 0
        text_sizes[text_size] += text_len

        if not (text_end in text_ends):
            text_ends[text_end] = 0
        text_ends[text_end] += 1
        
    return max(text_sizes, key=text_sizes.get), max(text_ends, key=text_ends.get)

def lines_to_paragraphs(lines, text_size, end_pos):
    paragraphs = []
    current_paragraph_spans = []
    current_paragraph_size = lines[0][0]['size']
    for line in lines:

        # If a new size comes, create a new paragraph
        if not same(line[0]['size'], current_paragraph_size, UNCERTAINTY_SIZE):
            paragraphs.append({
                'size': current_paragraph_size,
                'spans': current_paragraph_spans
            })
            current_paragraph_spans = []
            current_paragraph_size = line[0]['size']
        
        # Add the spans to the current paragraph
        for span in line:
            current_paragraph_spans.append({
                'text': span['text'],
                'size': span['size'],
                'flags': span['flags']
            })

        # Remove '-' from line break if a word got cut
        if current_paragraph_spans[-1]['text'][-1] == '-':
            current_paragraph_spans[-1]['text'] = current_paragraph_spans[-1]['text'][:-1]
        elif current_paragraph_spans[-1]['text'][-1] != ' ':
            current_paragraph_spans[-1]['text'] = current_paragraph_spans[-1]['text'] + ' '

        # End the paragraph if the lines doesn't go until the end
        if line[-1]['x_end'] <= end_pos - UNCERTAINTY_END and line[0]['size'] <= text_size + UNCERTAINTY_SIZE:
            paragraphs.append({
                'size': current_paragraph_size,
                'spans': current_paragraph_spans
            })
            current_paragraph_spans = []
            current_paragraph_size = line[0]['size']
    
    # Add the last paragraph
    paragraphs.append({
        'size': current_paragraph_size,
        'spans': current_paragraph_spans
    })

    return paragraphs

def combine_spans(paragraphs, text_size):

    def inner_combine(paragraph):
        paragraph_text = ''
        for span in paragraph['spans']:
            text = span['text']
            flags = get_flags(span['flags'])
            if 'italic' in flags:
                text = '<i>' + text + '</i>'
            if 'bold' in flags:
                text = '<b>' + text + '</b>'
            if 'monospaced' in flags:
                text = '<tt>' + text + '</tt>'
            if 'superscript' in flags:
                text = '<sup>' + text + '</sup>'
            if span['size'] < text_size:
                text = '<small>' + text + '</small>'
            paragraph_text += text
        return {
            'size': paragraph['size'],
            'text': paragraph_text
        }
    
    return list(map(inner_combine, paragraphs))

def paragraphs_to_chapters(paragraphs, text_size, book_title):
    chapters = []
    current_chapter_title = book_title
    current_chapter_content = ''

    for paragraph in paragraphs:
        
        # If the text size is great, create a new chapter
        if paragraph['size'] >= text_size + UNCERTAINTY_SIZE:
            chapters.append({
                'title': current_chapter_title,
                'content': current_chapter_content
            })
            current_chapter_title = paragraph['text']
            current_chapter_content = ''

        # Else add the paragraph
        else:
            current_chapter_content += '<p>' + paragraph['text'] + '</p>'
        
    # Add final chapter
    chapters.append({
        'title': current_chapter_title,
        'content': current_chapter_content
    })

    # If the first chapter is empty, just discard it.
    if chapters[0]['content'] == '':
        return chapters[1:]
    return chapters

def get_chapters(pdf, book_title, starting_page, pagenumber_start, pagenumberredex):
    
    # Get PDF Content
    spans = get_spans(pdf, starting_page=starting_page, pagenumber_start=pagenumber_start, pagenumberredex=pagenumberredex)
    lines = group_spans_in_lines(spans)

    # Find Constants for text size and line width
    text_size, end_pos = get_text_constants(lines)
    print(f'Found standart text size of {text_size} and text width of {end_pos}')

    # Create Chapters
    paragraphs = lines_to_paragraphs(lines, text_size, end_pos)
    paragraphs = combine_spans(paragraphs, text_size)
    chapters = paragraphs_to_chapters(paragraphs, text_size, book_title)

    return chapters

#######################
#--> Main

def main():
    pdf = fitz.open(args.file)
    book = epub.EpubBook()

    # Metadata
    book.set_title(args.title)
    book.add_author(args.author)
    book.set_language(args.language)
    book.set_identifier(''.join(random.choice(['0','1','2','3','4','5','6','7','8','9']) for i in range(30)))

    # Cover
    if args.cover != 0:
        cover_page = pdf[args.cover-1]
        for block in cover_page.get_text('dict')['blocks']:
            if block['type'] == 1: # Image
                save_image(cover_page, block['bbox'], 'cover')
    if os.path.exists('tmp/img-cover.jpeg'):
        with open('tmp/img-cover.jpeg', 'rb') as c:
            book.set_cover('cover.jpeg', c.read())

    # Content
    chapters = get_chapters(pdf, args.title, args.first, args.pagenumberstart, args.pagenumberredex)

    contents = []
    for nr, chapter in enumerate(chapters):
        title = chapter['title']
        html = '<h1>' + title + '</h1>' + chapter['content']
        ch = epub.EpubHtml(title=re.sub('<..?.?>', '', title), file_name=f'ch-{nr}.xhtml', lang='de')
        ch.set_content(html)
        book.add_item(ch)
        contents.append(ch)
    
    for image_path in os.listdir('tmp'):
        img = epub.EpubImage()
        img.file_name = image_path
        img.media_type = 'image/jpeg'
        with open('tmp/' + image_path, 'rb') as img_file:
            img.content = img_file.read()
        book.add_item(img)
    
    style = 'body { font-family: Times, Times New Roman, serif; }'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(nav_css)

    # Navigation & Extras
    book.toc = contents
    book.spine = ['nav'] + contents
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write & Clean up
    epub.write_epub(args.file[:-3] + 'epub', book)

    for file in os.listdir('tmp'):
        if file.endswith('.jpeg'):
            os.remove('tmp/' + file)

if __name__ == '__main__':
    main()