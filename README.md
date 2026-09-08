# AI VTuber (LLM ในเครื่อง + เสียงไทย + อวตาร Live2D)

VTuber ที่ขับเคลื่อนด้วย LLM ที่รัน **ในเครื่องนี้** (offline) พูดคุยภาษาไทย มีเสียงพูด
อวตารใน VTube Studio ขยับปากตามเสียง และเมื่อเจองานเขียนโค้ดที่ยากมาก จะส่งต่อให้
**Claude Code** (`claude -p`) ทำแทนโดยอัตโนมัติ

```
พิมพ์ข้อความ → router → LLM ในเครื่อง (LM Studio) ─┬─► ตอบเอง
                                                  └─► งานยาก → claude -p → สรุปผล
        → TTS ภาษาไทย (F5-TTS-THAI / MMS) → เล่นเสียง + ขับปากอวตาร (VTube Studio API)
```

เวอร์ชันนี้ (v1): **พิมพ์แชท + เสียงออก + ปากขยับ** · ยังไม่รับเสียงไมค์ (STT อยู่ใน v2)

---

## สเปคเครื่องที่ออกแบบมาให้ (ของเครื่องนี้)

| | |
|---|---|
| GPU | AMD Radeon RX 6700 XT 12 GB → LLM รันผ่าน **LM Studio (Vulkan)**; TTS รันบน **CPU** (AMD บน Windows ไม่มี PyTorch ROCm) |
| CPU / RAM | Ryzen 5 5600 · 24 GB |
| OS | Windows 10 |

---

## ติดตั้งครั้งแรก

> **สถานะเครื่องนี้:** `.venv` + แพ็กเกจหลัก + F5-TTS-THAI + ffmpeg 9.0.1 + Claude Code CLI
> + แอป LM Studio — **ติดตั้งแล้ว** เหลือแค่ข้อ 2 (เปิด LM Studio ตั้งค่า) กับข้อ 3 (VTube Studio)

### 1) Python env + แพ็กเกจหลัก  ✅ ติดตั้งแล้ว
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# ถ้าจะลงเครื่องใหม่ให้เป๊ะเหมือนเดิม:  pip install -r requirements-lock.txt
```

### 2) LM Studio (สมองของ VTuber)  — ⬅️ แอปลงแล้ว เหลือตั้งค่า
1. เปิดแอป **LM Studio** (ลงไว้ที่ `%LOCALAPPDATA%\Programs\LM Studio`) ครั้งแรกกดผ่าน onboarding
2. Settings → เลือก runtime **Vulkan** (ต้องเห็น "Radeon RX 6700 XT")
3. ค้น + ดาวน์โหลดโมเดล GGUF (เลือกอย่างใดอย่างหนึ่ง):
   - `scb10x/llama3.1-typhoon2-8b-instruct` — **ภาษาไทยดีที่สุด** (Q4_K_M ~5 GB)
   - `bartowski/Qwen2.5-7B-Instruct-GGUF` — สำรอง
4. แท็บ **Developer** → **Start Server** (พอร์ต 1234) → โหลดโมเดลที่ดาวน์โหลดไว้
5. เอาชื่อโมเดล (ตามที่ LM Studio แสดง) ไปใส่ `config.yaml` → `llm.model`

### 3) VTube Studio (อวตาร)  — ❗ ต้องลงเอง (เป็นเกมใน Steam)
1. ติดตั้งจาก Steam (ฟรี) — ไม่มีทางลงผ่าน CLI
2. Settings (ไอคอนเฟือง) → เลื่อนหา **Start API** → เปิด (พอร์ต 8001)
3. โหลดโมเดล Live2D — ใช้โมเดลตัวอย่างที่ให้มาก็ได้ (เช่น "Akari") ที่มีพารามิเตอร์ปากมาตรฐาน
4. ครั้งแรกที่รันแอปนี้ จะมี popup ใน VTube Studio → กด **Allow** (token ถูกเก็บไว้ที่ `.vts_token`)

### 4) ffmpeg  ✅ ติดตั้งแล้ว (9.0.1 — เปิดเทอร์มินัลใหม่ให้ PATH อัปเดต)

### 5) Claude Code CLI  ✅ ติดตั้งแล้ว (2.1.263) — เหลือแค่ login
```powershell
claude            # รันครั้งเดียวเพื่อ login (subscription หรือ API key)
```

### 6) เสียงตัวละคร F5-TTS-THAI  ✅ แพ็กเกจติดตั้งแล้ว
> ⚠️ **บนเครื่องนี้ (AMD GPU, ไม่มี CUDA) F5 ช้ามาก ~6 นาที/ประโยค** — เหมาะกับอัดเสียง
> ล่วงหน้าเท่านั้น ไม่เหมาะแชทสด · แชทสดใช้ `mms` (เร็ว เสียงเดียว)

ถ้าจะใช้เสียงตัวเอง วางไฟล์ (ไม่ใส่ก็ได้ — จะใช้เสียงตัวอย่างจาก repo อัตโนมัติ):
- `assets/voice_ref/ref.wav` — เสียงพูดไทยชัด 2–8 วิ (mono, 24 kHz)
- `assets/voice_ref/ref.txt` — ข้อความที่พูดในไฟล์นั้นแบบเป๊ะ ๆ

(ดู `assets/voice_ref/README.md`)

### 7) โหลดโมเดล TTS ล่วงหน้า (ไม่บังคับ)
```powershell
python scripts/download_models.py          # MMS
python scripts/download_models.py --f5      # + F5-TTS-THAI
```

---

## เช็กความพร้อม
```powershell
python scripts/setup_check.py
```

## รัน
```powershell
python run.py
```

### คำสั่งในแอป
| คำสั่ง | ทำอะไร |
|--------|--------|
| `<พิมพ์ข้อความ>` | คุยกับ VTuber (คำตอบถูกอ่านออกเสียง + ปากขยับ) |
| `/say <ข้อความ>` | ให้พูดข้อความนี้ทันที (ทดสอบเสียง/ปาก) |
| `/voice mms` \| `/voice f5` | สลับเอนจินเสียง |
| `/project <path>` | ตั้งโฟลเดอร์ที่ Claude Code จะเข้าไปทำงาน |
| `/claude <งาน>` | ส่งงานให้ Claude Code ตรง ๆ |
| `/reload` | โหลด `config.yaml` ใหม่ + ล้างประวัติ |
| `/quit` | ออก |

การส่งงานให้ Claude เกิดได้ 2 ทาง: (1) พิมพ์คำใน `coding.trigger_phrases` เช่น "เรียก claude ...",
(2) โมเดลในเครื่องตัดสินใจเองแล้วปล่อยมาร์กเกอร์ `[[DELEGATE_TO_CLAUDE: ...]]`

---

## เอนจินเสียง

| | MMS-TTS (`mms`) | F5-TTS-THAI (`f5`) |
|---|---|---|
| คุณภาพ | พอฟังรู้เรื่อง หุ่นยนต์นิด ๆ | ธรรมชาติ โคลนเสียงจาก `ref.wav` ได้ |
| ความเร็ว (CPU เครื่องนี้) | **~0.4× realtime** (ประโยคละ 2–3 วิ) | **~6 นาที/ประโยค** (RTF ~83, ไม่มี CUDA) |
| ใช้แชทสดได้ไหม | ได้ | **ไม่ได้** — อัดเสียงล่วงหน้าเท่านั้น |
| ติดตั้ง | มากับ `requirements.txt` | `f5-tts-th` (ติดตั้งแล้ว) |
| ใช้เมื่อ | ค่าเริ่มต้น / คุยโต้ตอบ | อยากได้เสียงเฉพาะตัว แล้วอัดเก็บไว้ |

> **หมายเหตุ:** Coqui XTTS-v2 **ไม่รองรับภาษาไทย** จึงเลือกใช้ F5-TTS-THAI + MMS แทน

---

## แก้ปัญหา

- **"ต่อ LM Studio ไม่ได้"** → เปิดแอป LM Studio → Developer → Start Server; เช็กว่าชื่อ `llm.model` ตรงกับที่โหลด
- **ปากไม่ขยับ** → VTube Studio เปิด API หรือยัง? โมเดลมีพารามิเตอร์ `MouthOpen` ไหม (ถ้าใช้ชื่ออื่นให้แก้ `avatar.mouth_param`); กด Allow popup แล้วหรือยัง
- **ไม่มีเสียง** → เช็ก default output device ของ Windows; `python -c "import sounddevice; print(sounddevice.query_devices())"`
- **F5 ติดตั้งไม่ผ่าน / ชน torch** → ข้ามไปก่อน ใช้ `mms` ได้เต็มรูปแบบ
- **ภาษาไทยเพี้ยนในเทอร์มินัล** → ใช้ Windows Terminal; `run.py` ตั้ง UTF-8 ให้แล้ว
- **`claude` สั่งงานแล้ว error** → รัน `claude` เปล่า ๆ ครั้งนึงเพื่อ login ให้เรียบร้อยก่อน

---

## โครงสร้าง
```
run.py                  จุดเริ่ม
config.yaml             ตั้งค่าทั้งหมด
src/
  config.py             โหลด config + .env
  llm/  client.py       คุยกับ LM Studio (OpenAI API)
        persona.py      system prompt / บุคลิก
        router.py       chat vs ส่งงาน Claude
  tts/  manager.py      แบ่งประโยค + cache + เลือกเอนจิน
        mms.py          MMS-TTS ไทย
        f5_thai.py      F5-TTS-THAI (voice cloning)
  avatar/ vts_client.py  VTube Studio plugin API
          lipsync.py     เสียง → ค่าอ้าปาก
          player.py      เล่นเสียง + ขับปากให้ซิงก์
  coding/ claude_code.py subprocess `claude -p`
  app.py                event loop หลัก
scripts/ setup_check.py  เช็กความพร้อม
         download_models.py
```

## ต่อไป (v2+)
ไมค์ → STT (faster-whisper) · streaming TTS ลด latency · โมเดลโค้ดในเครื่องแยก · สีหน้า/อารมณ์ · หน้าจอควบคุมบนเว็บ
