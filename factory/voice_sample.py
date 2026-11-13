"""Makes two short Hindi voice samples (male, female) and plays the male one."""
import asyncio, os
from pathlib import Path
import edge_tts

OUT = Path(__file__).resolve().parent.parent / "Voice Samples"; OUT.mkdir(exist_ok=True)
TEXT = ("साल 1612। मुग़ल बादशाह जहाँगीर का दरबार। ख़्वाजा नेमतुल्लाह हरवी एक किताब में दावा करता है कि अफ़ग़ान, "
        "यानी पश्तून, बनी इसराईल की औलाद हैं। चार सौ साल बाद, लखनऊ के क़रीब मलीहाबाद में, एक साइंटिस्ट अफ़रीदी "
        "पठानों के ख़ून के नमूने लेती है, यह जानने के लिए कि यह कहानी सच है या नहीं।")
for voice, name in [("hi-IN-MadhurNeural", "Hindi MALE (Madhur).mp3"), ("hi-IN-SwaraNeural", "Hindi FEMALE (Swara).mp3")]:
    print("making", name, "...")
    asyncio.run(edge_tts.Communicate(TEXT, voice, rate="-4%").save(str(OUT / name)))
print("Saved in:", OUT)
os.startfile(str(OUT))
