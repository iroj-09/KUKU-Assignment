# Video Editor Handoff Guide — NLE Workflow

This guide explains how video editors can import Kuku Promo Discovery candidate markers and sequences directly into **DaVinci Resolve**, **Adobe Premiere Pro**, and **Final Cut Pro**.

---

## 1. DaVinci Resolve Import

DaVinci Resolve supports importing timeline markers directly from CSV files.

### Steps:
1. Open your project and navigate to the **Edit** page.
2. In the timeline pool, right-click your master episode timeline or create a new timeline.
3. Select **Timelines** $\rightarrow$ **Import** $\rightarrow$ **Timeline Markers from CSV...** (or right-click the timeline ruler and choose *Import Markers from CSV*).
4. Select `outputs/ranked_promos/top_10_davinci_markers.csv` (or the CSV downloaded from the React app).
5. **Result:**
   * All candidate promo windows will appear as colored marker spans on the timeline ruler.
   * **Cyan Markers:** Top-tier candidates ($\ge 75$ score).
   * **Green Markers:** High-potential baseline candidates.
   * Hovering over each marker reveals the candidate's rank, score, hook notes, and cliffhanger details.

---

## 2. Adobe Premiere Pro Import

### Steps:
1. Open your Premiere Pro project with the episode sequence loaded.
2. Go to **File** $\rightarrow$ **Import...** (or open the **Markers Window** `Window` $\rightarrow$ `Markers`).
3. Select `outputs/ranked_promos/top_10_premiere_markers.csv`.
4. Right-click the sequence and choose **Import Markers**.
5. **Result:**
   * The candidate in/out points appear directly as comment markers on the sequence.
   * Use the **Markers panel** to double-click any candidate to instantly jump the playhead to the hook (0s) or cliffhanger.

---

## 3. CMX 3600 EDL (Avid / Final Cut / Universal)

The CMX 3600 Edit Decision List (`top_10_promos.edl`) allows assembling an instant highlight reel.

### Steps:
1. In DaVinci Resolve, Premiere, or Final Cut, go to **File** $\rightarrow$ **Import** $\rightarrow$ **Timeline / EDL...**
2. Select `top_10_promos.edl`.
3. Link the source episode media files.
4. **Result:**
   * A pre-assembled sequence containing the cuts of all shortlisted promo clips sequentially, ready for pacing trims and audio sweetening!

---

## 4. Editorial Best Practices for Microdrama Promos

1. **Safety Padding:**
   * Screenplay timestamps are event-based. Add a **0.5s – 1.0s lead-in buffer** before the first dialogue line to ensure the actor's opening syllable is not clipped.
2. **Audio Cutting at Cliffhanger:**
   * When cutting on the final cliffhanger line, cut the audio abruptly (no reverb tail or music resolution) to create psychological urgency that drives viewers to click through.
3. **Pacing Check:**
   * Aim for **90–160 WPM** (Words Per Minute). Clips under 80 WPM require strong physical action to hold mobile attention; clips over 180 WPM may require on-screen dynamic subtitles for viewer comprehension.
