import fitz
from ebooklib import epub
from collections import Counter

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

parser.add_argument('-c', '--cover', type=int, default=1, metavar='N', help='the page of the cover image (-1 if none), default=1')
parser.add_argument('-f', '--first', type=int, default=2, metavar='N', help='the first page containing actual text to convert, default=2')
parser.add_argument('-s', '--image_scale', type=int, default=4, metavar='N', help='the multiplier for image resolution, default=4')
parser.add_argument('-l', '--language', type=str, default='de', metavar='', help='the specified language, default=de')
parser.add_argument('-p', '--pagenumbers', type=int, default=-1, metavar='', help='the page where page numbers start (-1 if none), default=-1')

args = parser.parse_args()

print(args.file)
print(args.title)
print(args.author)
print(args.cover)
print(args.first)
print(args.image_scale)
print(args.language)
print(args.pagenumbers)

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

def remove_pagenum(blocks):
    filtered_blocks = []
    for block in blocks:
        if not (len(block) == 1 and block[0]['text'].lstrip().isdecimal()):
            filtered_blocks.append(block)
    if len(blocks) > len(filtered_blocks)+1:
        print('WARNING: TOO MANY LINES REMOVED')
        print(blocks)
    return filtered_blocks

def htmlify(text):
    for (pat, sub) in HTML_CHARS:
        text = re.sub(pat, sub, text)
    return text

### Save Image

def save_image(page, bbox, img_nr):
    page.get_pixmap(matrix=fitz.Matrix(args.image_scale, args.image_scale), clip=bbox).pil_save(f'tmp/img-{img_nr}.jpeg')

### Spans & Lines

def extract_span(span):
    flags = get_flags(span['flags'])
    size = span['size']
    text = span['text']
    text = htmlify(text)
    if 'italic' in flags:
        text = f'<i>{text}</i>'
    if 'bold' in flags:
        text = f'<b>{text}</b>'
    if 'monospaced' in flags:
        text = f'<tt>{text}</tt>'
    if 'superscript' in flags:
        text = f'<sup>{text}</sup>'
    return {'text': text, 'size': round(size)}

def extract_line(line):
    text = ''
    size = -1
    for span in line['spans']:
        span_info = extract_span(span)
        text += span_info['text']
        if span_info['text'].lstrip() != '' and size == -1:
            size = span_info['size']
    end_pos = round(line['bbox'][2])
    return {'text': text.rstrip(), 'size': size, 'end_pos': end_pos}

def get_lines_from_block(page, pagenum, blocks, img_nr):
    page_blocks = []
    for block in blocks:
        block_lines = []

        # Handle TEXT Blocks
        if block['type'] == 0:
            for line in block['lines']:
                line_info = extract_line(line)
                if line_info['text'] != '':
                    block_lines.append(line_info)

        # Handle IMAGE Blocks
        if block['type'] == 1:
            save_image(page, block['bbox'], img_nr)
            block_lines.append({'text': f'<img width="90%" src="img-{img_nr}.jpeg"/>', 'size': 11, 'end_pos': -1})
            img_nr += 1

        page_blocks.append(block_lines)

    if args.pagenumbers-1 >= 0 and pagenum >= args.pagenumbers-1:
        page_blocks = remove_pagenum(page_blocks)

    page_lines = sum(page_blocks, []) # Flatten list of lists

    return page_lines, img_nr


def combine_all_lines(pdf):
    img_nr = 0
    lines = []
    for pagenum, page in enumerate(pdf.pages(args.first-1)):
        blocks = page.get_text('dict')['blocks']
        new_lines, img_nr = get_lines_from_block(page, pagenum+args.first-1, blocks, img_nr)
        lines += new_lines
    return lines

### Common Numbers

def get_common_numbers(lines):
    sizes = []
    end_poses = []
    for line in lines:
        sizes.append(line['size'])
        end_poses.append(line['end_pos'])
    s_c = Counter(sizes).most_common()
    ep_c = Counter(end_poses).most_common()
    return {'sizes': s_c, 'end_poses': ep_c}

### Paragraphs

def lines_to_paragraphs(lines, final_end_pose, end_pos_uncertainty):
    paragraphs = []

    # Current paragraph data
    current_p_text = ''
    current_p_size = lines[0]['size']

    # Go through every line
    for line in lines:

        # If a new paragraph starts
        if line['size'] != current_p_size:

            # Only save the paragraph if there is something to save
            if current_p_text:
                paragraphs.append({'text': current_p_text, 'size': current_p_size})
            
            # Reset current paragraph data
            current_p_text = ''
            current_p_size = line['size']
        
        # Add the current data
        current_p_text += line['text'] + ' '

        # If a word is split to the next line, remove the seperation
        if line['end_pos'] >= final_end_pose - end_pos_uncertainty and current_p_text[-2:] == '- ' and current_p_text[-3] != ' ':
            current_p_text = current_p_text[:-2]

        # If a line ends before it reaches the right side, a new paragraph starts
        if line['end_pos'] < final_end_pose - end_pos_uncertainty:
            paragraphs.append({'text': current_p_text, 'size': current_p_size})
            current_p_text = ''
            current_p_size = line['size']
            
    # Add the final paragraph
    paragraphs.append({'text': current_p_text, 'size': current_p_size})
    return paragraphs

def paragraphs_to_chapters(paragraphs, final_text_size, book_title, text_size_uncertainty):
    chapters = []
    title = book_title
    texts = []
    for para in paragraphs:
        if para['size'] > final_text_size + text_size_uncertainty:
            chapters.append({'title': title, 'texts': texts})
            title = para['text']
            texts = []
        elif para['size'] < final_text_size - text_size_uncertainty:
            texts.append('<small>' + para['text'] + '</small>')
        else:
            texts.append(para['text'])
    chapters.append({'title': title, 'texts': texts})
    return chapters

def get_chapters(pdf, book_title, end_pos_uncertainty=5, text_size_uncertainty=1):
    lines = combine_all_lines(pdf)
    commons = get_common_numbers(lines)
    final_text_size = commons['sizes'][0][0]
    final_end_pose  = commons['end_poses'][0][0]
    paragraphs = lines_to_paragraphs(lines, final_end_pose, end_pos_uncertainty)
    chapters = paragraphs_to_chapters(paragraphs, final_text_size, book_title, text_size_uncertainty)
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
    if args.cover != -1:
        cover_page = pdf[args.cover-1]
        for block in cover_page.get_text('dict')['blocks']:
            if block['type'] == 1: # Image
                save_image(cover_page, block['bbox'], 'cover')
        with open('tmp/img-cover.jpeg', 'rb') as c:
            book.set_cover('cover.jpeg', c.read())

    # Content
    chapters = get_chapters(pdf, args.title)

    contents = []
    for nr, chapter in enumerate(chapters):
        title = chapter['title']
        html = f'<h1>{title}</h1>'
        for para_text in chapter['texts']:
            html += f'<p>{para_text}</p>'
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