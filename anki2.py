import argparse
import base64
import json
import logging
import os
import re
import zlib

import markdown2
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Flashcard:
    EMBED_FILENAME_REGEX = r'!\[\[(.*?)\]\]'
    STATE_INSERT = 'INSERT'
    STATE_UPDATE = 'UPDATE'

    def __init__(self, front, back):
        self.medias = set()
        self.front = front
        self.back = back
        self.state = None
        self.back_html = None
        self.front_html = None
        self.card_sum = None
        self.checksum = None
        self.anki_id = None
        self._meta_value = None

    def analyze(self):
        self.anki_id, self.checksum, self._meta_value = self._extract_anki_meta(self.back)
        self.card_sum = self._generate_card_sum()

        if self.anki_id is None:
            self.state = Flashcard.STATE_INSERT
        elif str(self.card_sum) != self.checksum:
            self.state = Flashcard.STATE_UPDATE
        else:
            return

        self.front_html = self._convert_to_html(self.front)
        self.back_html = self._convert_to_html(self.back)
        self._extract_medias()

    def update_meta(self, origin):
        if self.state is None:
            return origin

        meta_value = f"<!--Meta:id={self.anki_id};sum={self.card_sum}-->"
        return origin.replace(self._meta_value, meta_value)

    @staticmethod
    def _extract_anki_meta(text):
        match = re.search(MarkdownFlashcardExtractor.ANKI_META_REGEX, text)
        if match:
            return match.group(1), match.group(2), match.group(0)
        return None, None, None

    def _extract_medias(self):
        self.medias.update(re.findall(Flashcard.EMBED_FILENAME_REGEX, self.front))
        self.medias.update(re.findall(Flashcard.EMBED_FILENAME_REGEX, self.back))

    def _generate_card_sum(self):
        data = re.sub(MarkdownFlashcardExtractor.ANKI_META_REGEX, '', self.back).strip()
        return zlib.crc32((self.front + data).encode('utf-8'))

    # noinspection RegExpRedundantEscape
    @staticmethod
    def _convert_to_html(markdown_text):
        html = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "break-on-newline"])
        return re.sub(Flashcard.EMBED_FILENAME_REGEX, lambda match: f"<img src='{match.group(1)}' />", html)


class MarkdownFlashcardExtractor:
    FLASHCARD_SEPARATOR = '---'
    ANKI_META_REGEX = r'<!--Meta:id=(\d+)(?:;sum=(-?\d+))?-->'
    FLASHCARD_REGEX = r'(?i)#flashcard\s*'

    def __init__(self, file_path):
        self.file_path = file_path

    def extract_flashcards(self):
        content = self._read_file(self.file_path)
        return self._parse_flashcards(content), content

    @staticmethod
    def _read_file(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    def _parse_flashcards(self, content):
        cards_raw = content.split(self.FLASHCARD_SEPARATOR)
        flashcards = []
        for card_raw in cards_raw:
            parts = re.split(self.FLASHCARD_REGEX, card_raw)
            if len(parts) == 2:
                front, back = parts
                flashcards.append(Flashcard(front.strip(), back.strip()))
        return flashcards


class AnkiConnect:
    DEFAULT_DECK = "Default"
    DEFAULT_MODEL = "Basic"

    def __init__(self, deck_name=DEFAULT_DECK, model_name=DEFAULT_MODEL, endpoint='http://localhost:8765'):
        self.deck_name = deck_name
        self.model_name = model_name
        self.endpoint = endpoint

    def invoke(self, action, **params):
        request = {'action': action, 'version': 6, 'params': params}
        logger.debug(f"invoke start action={action}")
        response = requests.post(self.endpoint, json=request)
        data = response.json()
        logger.debug(f"invoke action={action}, response {data}")
        return data

    def deck_names(self):
        resp = self.invoke('deckNames')
        if 'result' in resp:
            return resp['result']
        return []

    def create_deck(self):
        return self.invoke('createDeck', deck=self.deck_name)

    def update_note(self, note_id, front, back):
        note = {"id": note_id, "fields": {"Front": front, "Back": back}}
        return self.invoke("updateNoteFields", note=note)

    def add_note(self, front, back):
        note = {
            'deckName': self.deck_name,
            'modelName': self.model_name,
            'fields': {'Front': front, 'Back': back},
            'options': {'allowDuplicate': False},
            'tags': []
        }
        return self.invoke('addNote', note=note)

    def add_media_file(self, filename, file_base64):
        return self.invoke('storeMediaFile', filename=os.path.basename(filename), data=file_base64)


class AttachmentManager:
    def __init__(self, vault_path):
        self.vault_path = vault_path
        self.dict_cache = None

    def _build_attachment_dict(self):
        logger.debug(f"building attachment dict")
        attachment_folder = self._extract_attachment_folder_path()
        if not attachment_folder:
            logger.info("Could not find or read the attachment folder path from app.json.")
            return {}

        attachment_path = os.path.join(self.vault_path, attachment_folder)
        attachment_dict = {}
        for root, _, files in os.walk(attachment_path):
            for filename in files:
                full_path = os.path.join(root, filename)
                relative_path = os.path.relpath(full_path, self.vault_path)
                attachment_dict[filename] = relative_path
        return attachment_dict

    def _extract_attachment_folder_path(self):
        app_json_path = os.path.join(self.vault_path, '.obsidian', 'app.json')
        try:
            with open(app_json_path, 'r') as file:
                app_config = json.load(file)
                return app_config.get('attachmentFolderPath', '')
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"An error occurred while reading the app.json: {e}")
            return ''

    @property
    def attachment_dict(self):
        if self.dict_cache is None:
            self.dict_cache = self._build_attachment_dict()

        return self.dict_cache

    def get_file_base64_content(self, filename):
        if filename in self.attachment_dict:
            file_path = os.path.join(self.vault_path, self.attachment_dict[filename])
            try:
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                    return base64.b64encode(file_content).decode('utf-8')
            except FileNotFoundError:
                logger.error(f"File not found: {file_path}")
            except IOError as e:
                logger.error(f"Could not read file: {file_path}. Error: {e}")
        else:
            logger.error(f"Filename {filename} does not exist in the attachment dictionary.")
        return None


class CardMarker:
    def __init__(self, anki_connect, attachment_manager):
        self._anki_connect = anki_connect
        self.attachment_manager = attachment_manager

    def make_cards(self, markdown_file):
        extractor = MarkdownFlashcardExtractor(markdown_file)
        flashcards, original_content = extractor.extract_flashcards()
        for flashcard in flashcards:
            flashcard.analyze()
            if flashcard.state is None:
                logger.debug(f"Skipping flashcard {flashcard.anki_id}")
                continue

            self.sync_card(flashcard)
        return flashcards, original_content

    # noinspection PyTypeChecker
    def sync_card(self, flashcard):
        if flashcard.state == Flashcard.STATE_UPDATE:
            self._anki_connect.update_note(int(flashcard.anki_id), flashcard.front_html, flashcard.back_html)
        elif flashcard.state == Flashcard.STATE_INSERT:
            result = self._anki_connect.add_note(flashcard.front_html, flashcard.back_html)
            if 'result' in result:
                new_id = result['result']
                flashcard.anki_id = new_id

    def sync_medias(self, flashcards):
        medias = set()
        [medias.update(flashcard.medias) for flashcard in flashcards]

        if len(medias) == 0:
            return

        for media in medias:
            base64_attach = self.attachment_manager.get_file_base64_content(media)
            if base64_attach:
                self._anki_connect.add_media_file(media, base64_attach)


def enable_debug_logging():
    logger.setLevel(logging.DEBUG)
    logging.getLogger("requests").setLevel(logging.DEBUG)
    logging.getLogger("markdown2").setLevel(logging.DEBUG)


def prepare_deck(deck_name, anki_connect):
    decks = anki_connect.deck_names()
    if deck_name not in decks:
        anki_connect.create_deck(deck_name)


def update_content(flashcards, original_content, file_path):
    data = original_content
    for flashcard in flashcards:
        data = flashcard.update_meta(data)

    if data != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data)


# noinspection PyTypeChecker
def main(vault_path, note_path, enable_debug=False, deck_name=AnkiConnect.DEFAULT_DECK,
         model_name=AnkiConnect.DEFAULT_MODEL):
    if enable_debug:
        enable_debug_logging()

    markdown_file_path = os.path.join(vault_path, note_path)
    markdown_files = [file for file in os.listdir(markdown_file_path) if file.endswith(('.md', '.markdown'))]

    anki_connect = AnkiConnect(deck_name, model_name)
    attachment_manager = AttachmentManager(vault_path)
    card_marker = CardMarker(anki_connect, attachment_manager)
    prepare_deck(deck_name, anki_connect)
    for markdown_file in markdown_files:
        file_path = os.path.join(markdown_file_path, markdown_file)
        flashcards, content = card_marker.make_cards(file_path)
        card_marker.sync_medias(flashcards)
        update_content(flashcards, content, file_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sync Obsidian flashcards with Anki')
    parser.add_argument('vault_path', help='The file path to the Obsidian vault')
    parser.add_argument('note_path', help='The path to the note folder within the vault')
    parser.add_argument('--deck_name', help='The name of the Anki deck (optional)')
    parser.add_argument('--model_name', default=AnkiConnect.DEFAULT_MODEL, help='The name of the Anki model (optional)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.deck_name is None:
        args.deck_name = args.note_path.replace('/', '::')

    main(args.vault_path, args.note_path, args.debug, args.deck_name, args.model_name)
