### markdown card style

cards seperated by `---`, front and back seperated by `#flashcard`

```markdown
观放白鹰二首 
唐⋅ 李白 #flashcard 

【其一】 
八月边风高，胡鹰白锦毛。 
孤飞一片雪，百里见秋毫。 
【其二】 
寒冬十二月，苍鹰八九毛。 
寄言燕雀莫相啅，自有云霄万里高。

---

十一月四日风雨大作（其一）
宋⋅ 陆游 #flashcard 

风卷江湖雨暗村，四山声作海涛翻。 
溪柴火软蛮毡暖，我与狸奴不出门。

---
```

### How to Use

```bash
usage: anki2.py [-h] [--deck_name DECK_NAME] [--model_name MODEL_NAME] [--debug] vault_path note_path

Sync Obsidian flashcards with Anki

positional arguments:
  vault_path            The file path to the Obsidian vault
  note_path             The path to the note folder within the vault

options:
  -h, --help            show this help message and exit
  --deck_name DECK_NAME
                        The name of the Anki deck (optional)
  --model_name MODEL_NAME
                        The name of the Anki model (optional)
  --debug               Enable debug logging
```

### Install Python dependency

Run pip install against the requirements.txt file to install the program dependencies in your system:

```bash
pip install -r requirements.txt
```

### Install AnkiConnect on Anki

- Tools > Add-ons -> Get Add-ons...
- Paste the code 2055492159 > Ok

