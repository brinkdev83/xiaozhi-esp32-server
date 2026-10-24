# Mochi: lokale server met Claude

Deze fork draait de xiaozhi-server op een Windows-pc voor een Waveshare
ESP32-S3-Touch-AMOLED-1.75 met de XiaoZhi-firmware (variant
`esp32-s3-touch-amoled-1.75-mochi`, zie de bijbehorende firmware-fork).

| Stap | Dienst |
| --- | --- |
| Spraakherkenning | OpenAI Whisper (`whisper-1`, taal `nl`) |
| Brein | Claude (`claude-opus-5-5`, effort `low`) via de officiële Anthropic SDK |
| Stem | Microsoft Edge TTS (`nl-NL-FennaNeural`) |

## Wat er is aangepast

- `main/xiaozhi-server/core/providers/llm/claude/claude.py`: Claude-provider
  (streaming, server-side fallback bij een weigering). Geen function calling,
  dus gebruik `Intent: nointent`.
- `main/xiaozhi-server/core/providers/asr/openai.py`: optionele `language`, en
  een lege `api_key` valt terug op `OPENAI_API_KEY`.
- `main/xiaozhi-server/data/.config.yaml`: Mochi-instellingen (Nederlands).
- `main/xiaozhi-server/data/mochi-prompt.txt`: eigen prompttemplate, zonder
  locatie- en weeropvragingen.
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

## Starten

`powershell -ExecutionPolicy Bypass -File start-server.ps1`, daarna het bord
aanzetten of resetten en "Hi ESP" zeggen.
