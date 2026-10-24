# Mochi: lokale server met Claude

Deze fork draait de xiaozhi-server op een Windows-pc voor een Waveshare
ESP32-S3-Touch-AMOLED-1.75 met de XiaoZhi-firmware (variant
`esp32-s3-touch-amoled-1.75-mochi`, zie de bijbehorende firmware-fork).
Mochi is een pratend huisdiertje: het heeft behoeften die met de tijd
veranderen, onthoudt gesprekken en reageert als je het apparaat schudt of oppakt.

| Stap | Dienst |
| --- | --- |
| Spraakherkenning | OpenAI Whisper (`whisper-1`, taal `nl`) |
| Brein | Claude Haiku 5.5 (`claude-haiku-5-5`, effort `low`, denken uit) met tool use |
| Stem | Microsoft Edge TTS (`nl-NL-FennaNeural`) |
| Geheugen | `mem_local_short`, samenvatting via Claude, lokaal in `data/` |

## Huisdier

- Behoeften 0-100 (hoger is beter): verzadigd, energie, plezier, schoon, plus
  de band met de gebruiker. Ze dalen per uur (energie herstelt tijdens slapen);
  offline tijd wordt tot 48 uur ingehaald. Opslag: `data/mochi_pet.json`.
- De toestand staat elke beurt in de systeemprompt (`{{pet_status}}`), zodat
  Mochi laat merken hoe het zich voelt.
- Tools die Claude aanroept: `mochi_eten`, `mochi_spelen`, `mochi_knuffelen`,
  `mochi_wassen`, `mochi_slapen`, `mochi_wakker` en `mochi_gebeurtenis`
  (geschud / opgepakt, gemeld door de firmware).

## Wat er is aangepast

- `core/providers/llm/claude/claude.py`: Claude-provider via de officiële
  Anthropic SDK: streaming, tool use voor `Intent: function_call` (de
  `direct_answer`-omweg van de server wordt gewone tekst), instelbaar denken en
  optionele server-side fallback (niet voor Haiku 5.5).
- `core/utils/mochi_pet.py` en `plugins_func/functions/mochi_pet.py`:
  huisdiertoestand en verzorgingstools.
- `core/utils/dialogue.py`, `core/utils/prompt_manager.py`: vullen
  `{{pet_status}}` per beurt in, zoals `{{current_time}}`.
- `core/providers/asr/openai.py`: optionele `language`, en een lege `api_key`
  valt terug op `OPENAI_API_KEY`.
- `data/.config.yaml`, `data/mochi-prompt.txt`: Nederlandse instellingen en
  prompttemplate, zonder locatie- en weeropvragingen.
- `start-server.ps1`: start de server met opus.dll en ffmpeg op het pad.

## Eenmalig installeren

1. Python 3.11, dan in de repo-root:
   `python -m venv .venv` en
   `.venv\Scripts\python -m pip install -r main\xiaozhi-server\requirements.txt anthropic pyogg`
2. ffmpeg: `winget install --id Gyan.FFmpeg -e`
3. Sleutels als gebruikersvariabelen (nooit in een bestand):
   `setx ANTHROPIC_API_KEY "..."` en `setx OPENAI_API_KEY "..."`
4. Firewall: netwerk op Privé en TCP 8000 en 8003 inkomend toestaan (Privé).
5. Pas in `data/.config.yaml` het IP-adres aan als de pc een ander adres krijgt
   (en bouw de firmware dan opnieuw met dat adres).
6. Automatisch starten bij inloggen: een snelkoppeling in de Windows-opstartmap
   (`shell:startup`) naar
   `powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File C:\dev\xiaozhi-server\start-server.ps1`.

## Starten

`powershell -ExecutionPolicy Bypass -File start-server.ps1`, daarna het bord
aanzetten of resetten en "Hi ESP" zeggen.
