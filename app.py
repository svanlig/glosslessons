from flask import Flask, render_template, request, jsonify
import requests
import xml.etree.ElementTree as ET
import sqlite3
import re
from datetime import datetime
import traceback

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('lessons.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS completed_lessons
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  lesson_name TEXT,
                  lesson_title TEXT,
                  language TEXT,
                  level TEXT,
                  topic TEXT,
                  completed_date TEXT)''')
    conn.commit()
    conn.close()

def parse_lesson_url(url):
    match = re.search(r'lessonName=([^&]+)', url)
    if match:
        return match.group(1)
    return None

def get_xml_url(lesson_name):
    return f"https://gloss.dliflc.edu/GlossHtml/templates/linksLO/glossLOs/{lesson_name}.xml"

def get_audio_url(lesson_name, audio_file):
    return f"https://gloss.dliflc.edu/products/gloss/{lesson_name}/media/{audio_file}"

def parse_xml(xml_content, lesson_name):
    try:
        print(f"Parsing XML for {lesson_name}")
        print(f"XML content length: {len(xml_content)}")
        
        root = ET.fromstring(xml_content)
        
        lesson_data = {
            'lesson_name': lesson_name,
            'title': '',
            'language': '',
            'level': '',
            'topic': '',
            'articles': [],
            'glossary': []
        }
        
        # Count all QREC elements
        qrecs = root.findall('.//QREC')
        print(f"Found {len(qrecs)} QREC elements")
        
        for qrec in qrecs:
            a_type = qrec.find('A_Type')
            if a_type is not None and a_type.text:
                a_type_text = a_type.text.strip()
                
                if a_type_text == 'GW':
                    title = qrec.find('OL_Title')
                    language = qrec.find('LANGUAGE')
                    level = qrec.find('LEVEL')
                    topic = qrec.find('TOPIC')
                    
                    if title is not None and title.text:
                        lesson_data['title'] = title.text.strip()
                    if language is not None and language.text:
                        lesson_data['language'] = language.text.strip()
                    if level is not None and level.text:
                        lesson_data['level'] = level.text.strip()
                    if topic is not None and topic.text:
                        lesson_data['topic'] = topic.text.strip()
                    
                    print(f"Lesson info - Title: {lesson_data['title']}, Language: {lesson_data['language']}")
                
                elif a_type_text == 'GG':
                    glos_left = qrec.findall('GlosLeft')
                    glos_right = qrec.findall('GlosRight')
                    audio_stimuli = qrec.findall('AUD_STIMULUS')
                    
                    print(f"Glossary - Left: {len(glos_left)}, Right: {len(glos_right)}, Audio: {len(audio_stimuli)}")
                    
                    audio_index = 0
                    if audio_stimuli and audio_stimuli[0].text.strip() == 'SELECT':
                        audio_index = 1
                    
                    for i in range(min(len(glos_left), len(glos_right))):
                        audio_url = ''
                        if audio_index < len(audio_stimuli):
                            audio_file = audio_stimuli[audio_index].text.strip()
                            if audio_file and audio_file != 'SELECT':
                                audio_url = get_audio_url(lesson_name, audio_file)
                            audio_index += 1
                        
                        word = glos_left[i].text.strip() if glos_left[i].text else ''
                        translation = glos_right[i].text.strip() if glos_right[i].text else ''
                        
                        lesson_data['glossary'].append({
                            'word': word,
                            'translation': translation,
                            'audio': audio_url
                        })
                
                elif a_type_text == 'CO':
                    articles_fl = qrec.findall('CO_ParaFL')
                    articles_xl = qrec.findall('CO_ParaXL')
                    audio_stimuli = qrec.findall('AUD_STIMULUS')
                    
                    print(f"Articles - FL: {len(articles_fl)}, XL: {len(articles_xl)}")
                    
                    for i in range(min(len(articles_fl), len(articles_xl))):
                        audio_url = ''
                        if i < len(audio_stimuli):
                            audio_file = audio_stimuli[i].text.strip()
                            if audio_file and audio_file != 'SELECT' and audio_file != 'No Video File':
                                audio_url = get_audio_url(lesson_name, audio_file)
                        
                        fl_text = articles_fl[i].text.strip() if articles_fl[i].text else ''
                        xl_text = articles_xl[i].text.strip() if articles_xl[i].text else ''
                        
                        lesson_data['articles'].append({
                            'fl': fl_text,
                            'xl': xl_text,
                            'audio': audio_url
                        })
        
        print(f"Final - Articles: {len(lesson_data['articles'])}, Glossary: {len(lesson_data['glossary'])}")
        return lesson_data
        
    except Exception as e:
        print(f"Error parsing XML: {e}")
        traceback.print_exc()
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/load_lesson', methods=['POST'])
def load_lesson():
    url = request.json.get('url')
    lesson_name = parse_lesson_url(url)
    
    print(f"Loading lesson: {lesson_name}")
    print(f"From URL: {url}")
    
    if not lesson_name:
        return jsonify({'error': 'Invalid URL format. Could not find lessonName parameter.'}), 400
    
    xml_url = get_xml_url(lesson_name)
    print(f"Fetching XML from: {xml_url}")
    
    try:
        response = requests.get(xml_url, timeout=10)
        print(f"Response status: {response.status_code}")
        
        response.raise_for_status()
        
        print(f"Response content length: {len(response.content)}")
        print(f"Content type: {response.headers.get('content-type')}")
        
        lesson_data = parse_xml(response.content, lesson_name)
        if lesson_data:
            print("Successfully parsed lesson data")
            return jsonify(lesson_data)
        else:
            print("Failed to parse XML data")
            return jsonify({'error': 'Failed to parse XML data.'}), 500
            
    except requests.RequestException as e:
        print(f"Request error: {e}")
        return jsonify({'error': f'Failed to fetch XML: {str(e)}'}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/search_lessons', methods=['POST'])
def search_lessons():
    data = request.json
    language_id = data.get('languageId', 19)
    page = data.get('page', 1)
    
    try:
        form_data = {
            'action': 'search',
            'gr': '0',
            'page': str(page),
            'searchString': '',
            'languageIds': str(language_id),
            'levelIds': '',
            'modalityIds': '',
            'competenceIds': '',
            'topicIds': '',
            'subTopicIds': '',
            'video': '0',
            'statusIds': '',
            'mine': '0',
            'sortBy': 'newest'
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        print(f"Searching lessons - Language ID: {language_id}, Page: {page}")
        
        response = requests.post(
            'https://gloss.dliflc.edu/LessonJSON.aspx',
            data=form_data,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        print(f"Search response status: {response.status_code}")
        
        return jsonify(response.json())
        
    except requests.RequestException as e:
        print(f"Search request error: {e}")
        return jsonify({'error': f'Failed to search lessons: {str(e)}'}), 500
    except Exception as e:
        print(f"Search unexpected error: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/complete_lesson', methods=['POST'])
def complete_lesson():
    data = request.json
    conn = sqlite3.connect('lessons.db')
    c = conn.cursor()
    c.execute('''INSERT INTO completed_lessons 
                 (lesson_name, lesson_title, language, level, topic, completed_date)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (data.get('lesson_name', ''),
               data.get('title', ''),
               data.get('language', ''),
               data.get('level', ''),
               data.get('topic', ''),
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/get_completed_lessons')
def get_completed_lessons():
    conn = sqlite3.connect('lessons.db')
    c = conn.cursor()
    c.execute('''SELECT lesson_name, lesson_title, language, level, topic, completed_date 
                 FROM completed_lessons 
                 ORDER BY completed_date DESC''')
    lessons = c.fetchall()
    conn.close()
    
    grouped = {}
    for lesson in lessons:
        lang = lesson[2] or 'Unknown'
        if lang not in grouped:
            grouped[lang] = []
        grouped[lang].append({
            'lesson_name': lesson[0],
            'title': lesson[1],
            'level': lesson[3],
            'topic': lesson[4],
            'date': lesson[5]
        })
    
    return jsonify(grouped)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=8000)
