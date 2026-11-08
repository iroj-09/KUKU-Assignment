"""Browser smoke test of the React review app (real Chrome, every tab and the main flows).

Needs (optional, not in requirements.txt):   pip install playwright    and Google Chrome installed.
Needs the 50-episode pack in data/input and a built app with the sample data:

    python scripts/sync_frontend_data.py
    cd frontend && npm run build && npx vite preview --port 4180 &
    python scripts/ui_smoke_test.py            # BASE_URL env var overrides http://localhost:4180/

Checks: data loads, all tabs open, Explorer counts, Simulator plays and resets, Compare shows model scores,
Review save/backup/import, Export downloads, Upload add/remove/generate/restore, batch-AI abort on a bad key
and cancel (the Gemini API is mocked), and no horizontal overflow on a phone-width screen.
Exit code 1 if any check fails; failing screenshots go to the temp folder printed at the end.
"""
import json
import os
import tempfile
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:4180/")
ROOT = Path(__file__).resolve().parent.parent
SCRATCH = Path(tempfile.mkdtemp(prefix="kuku_ui_test_"))
EP1 = ROOT / "data" / "input" / "episode-001-Episode 1671703.txt"
EP2 = ROOT / "data" / "input" / "episode-002-Episode 1671704.txt"

results = []
console_errors = []


def step(name):
    def deco(fn):

        try:
            fn()
            results.append((name, True, ""))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {str(e)[:300]}"))
            try:
                page.screenshot(path=str(SCRATCH / f"fail_{re.sub('[^a-z0-9]+', '_', name.lower())}.png"))
            except Exception:  # noqa: BLE001
                pass
        return fn
    return deco


def expect(cond, msg="assertion failed"):
    if not cond:
        raise AssertionError(msg)


def tab(label):
    page.get_by_role("button", name=re.compile(label)).first.click()
    page.wait_for_timeout(300)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1400, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = ctx.new_page()
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))

    @step("1 app loads with pipeline data")
    def _():
        page.goto(BASE)
        page.wait_for_selector("text=KUKU PROMO STUDIO", timeout=15000)
        page.wait_for_selector("text=Find the promos worth posting", timeout=15000)
        # Home: nothing chosen yet, so the header carries no drama numbers
        expect("Episodes:" not in page.inner_text("header"), "Home header should not show drama stats")
        # ...they appear on the drama's own pages
        tab("Overview")
        page.wait_for_selector("text=Broken Soldier")
        txt = page.inner_text("header")
        expect(re.search(r"Episodes:\s*50", txt) and "60 clips" in txt, "header stats on Overview: " + txt[:200])
        tab("Home")  # the next step starts from Home
        page.wait_for_selector("text=Find the promos worth posting")

    @step("1b home: two options, each opens its own page")
    def _():
        body = page.inner_text("body")
        expect("I Married a Broken Soldier. He was a Duke." in body, "drama name is the title of option 1")
        expect("Upload a new drama" in body and "Explore existing results" not in body, "option 2 + no generic title")
        card = page.get_by_role("button", name="Open existing results")
        expect(card.is_enabled(), "existing-results card enabled")
        expect("60" in card.inner_text() and "50" in card.inner_text(), "card shows the real stats")
        card.click()
        page.wait_for_selector("text=Broken Soldier", timeout=5000)          # Overview page
        tab("Home")
        page.get_by_role("button", name="Upload and generate").click()
        page.wait_for_selector("text=Upload & Generate Promo Clips", timeout=5000)  # upload page
        expect(page.locator(".fixed.inset-0").count() == 0, "upload is a page, not a floating dialog")
        page.get_by_role("button", name=re.compile("Back")).click()
        page.wait_for_selector("text=Find the promos worth posting", timeout=5000)

    @step("2 every tab opens")
    def _():
        for label, marker in [
            ("Home", "Find the promos worth posting"),
            ("Promo Explorer", "Candidate Leaderboard (60)"),
            ("Phone Simulator", "Previewing Vertical Promo"),
            ("Compare Battle", "Promo Comparison Battle"),
            ("Editorial Review", "Human Editorial Sign-Off"),
            ("Export NLE", "Export & NLE Delivery Station"),
            ("Overview", "Broken Soldier"),
        ]:
            tab(label)
            page.wait_for_selector(f"text={marker}", timeout=5000)

    @step("3 explorer: filters show real counts, nothing hidden by default")
    def _():
        tab("Promo Explorer")
        opts = page.locator("select option").all_inner_texts()
        expect(any("PASS Only (46)" in o for o in opts), str(opts[:12]))
        expect(any("PARTIAL (14)" in o for o in opts), "PARTIAL count")
        expect(any("All 50 Episodes" in o for o in opts), "episode count option")
        expect(any("UNVERIFIED (0)" in o for o in opts), "UNVERIFIED option")

    @step("4 simulator: plays, advances, resets when clip changes")
    def _():
        tab("Phone Simulator")
        page.wait_for_selector("text=Previewing Vertical Promo")

        def clock():
            m = re.search(r"(\d+\.\d)s / (\d+\.\d)s", page.inner_text("body"))
            return float(m.group(1)), float(m.group(2))

        expect(clock()[0] == 0.0, "starts at 0")
        page.locator("button:has(svg.lucide-play)").first.click()
        page.wait_for_timeout(1800)
        t1, dur = clock()
        expect(t1 >= 1.0, f"time should advance, got {t1}")
        page.locator("button:has(svg.lucide-pause)").first.click()
        expect(dur > 20, f"duration {dur}")
        page.select_option("select", index=2)
        page.wait_for_timeout(400)
        expect(clock()[0] == 0.0, "time must reset on clip change, got %s" % clock()[0])
        expect(page.locator("button:has(svg.lucide-play)").count() >= 1, "paused after clip change")
        body = page.inner_text("body")
        expect("INSTANT HOOK WINDOW" in body, "hook window banner at t=0")

    @step("4b simulator: stops at the end, and play on a finished clip replays it")
    def _():
        tab("Phone Simulator")
        page.wait_for_selector("text=Previewing Vertical Promo")

        def clock():
            m = re.search(r"(\d+\.\d)s / (\d+\.\d)s", page.inner_text("body"))
            return float(m.group(1)), float(m.group(2))

        dur = clock()[1]
        slider = page.locator("input[type=range]").first
        slider.evaluate(
            "(el, v) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            " set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); }",
            str(round(dur - 0.3, 1)),
        )
        page.locator("button:has(svg.lucide-play)").first.click()
        page.wait_for_timeout(1200)
        t, _ = clock()
        expect(t >= dur - 0.05, f"should have reached the end ({t} of {dur})")
        expect(page.locator("button:has(svg.lucide-play)").count() >= 1, "shows Play again once finished")
        page.locator("button:has(svg.lucide-play)").first.click()   # replay
        page.wait_for_timeout(700)
        t2, _ = clock()
        expect(0.2 < t2 < 3.0, f"replay should restart near 0, got {t2}")

    @step("5 compare: shows model dimension scores, not heuristic ones")
    def _():
        tab("Compare Battle")
        page.wait_for_selector("text=Promo Comparison Battle")
        body = page.inner_text("body")
        nums = [float(x) for x in re.findall(r"Hook Impact:\s*\n?\s*([0-9.]+)\s*/ 10", body)]
        expect(nums and min(nums) >= 5, f"hook scores should be the model's (>=5 typically), got {nums}")

    @step("6 review: save decision, backup JSON, wipe, import")
    def _():
        tab("Editorial Review")
        page.get_by_role("radio", name=re.compile("Approve for Edit")).click()
        page.get_by_role("button", name=re.compile("Save Review Decision")).click()
        page.wait_for_selector("text=1 Approved")
        with page.expect_download() as dl:
            page.get_by_role("button", name=re.compile("Backup Reviews")).click()
        path = SCRATCH / "reviews_backup.json"
        dl.value.save_as(str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        expect(len(data["reviews"]) == 1, "one review in backup")
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_selector("header")
        tab("Editorial Review")
        expect("0 Approved" in page.inner_text("body"), "state wiped")
        page.locator("input[type=file][accept*='json']").set_input_files(str(path))
        page.wait_for_selector("text=Imported 1 review", timeout=5000)
        page.wait_for_selector("text=1 Approved")
        # a junk file must be rejected, not crash
        bad = SCRATCH / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        page.locator("input[type=file][accept*='json']").set_input_files(str(bad))
        page.wait_for_selector("text=Import failed", timeout=5000)

    @step("7 export: DaVinci CSV and EDL download with the right content")
    def _():
        tab("Export NLE")
        with page.expect_download() as dl:
            page.get_by_role("button", name=re.compile("DaVinci")).click()
        f = SCRATCH / "dv.csv"
        dl.value.save_as(str(f))
        lines = f.read_text(encoding="utf-8").strip().splitlines()
        expect(len(lines) == 11, f"header + 10 rows, got {len(lines)}")
        with page.expect_download() as dl:
            page.get_by_role("button", name=re.compile("EDL")).first.click()
        f = SCRATCH / "x.edl"
        dl.value.save_as(str(f))
        txt = f.read_text(encoding="utf-8")
        expect("FCM: NON-DROP FRAME" in txt and "001  AX" in txt, "edl structure")

    @step("8 upload: add 2 files, remove one, generate -> only uploaded shown, chips removable")
    def _():
        tab("Overview")
        page.get_by_role("button", name=re.compile("Upload & Generate")).first.click()
        fi = page.locator("input[type=file][accept*='.txt']")
        fi.set_input_files([str(EP1), str(EP2)])
        page.wait_for_selector("text=Selected Files (2)")
        page.get_by_label(re.compile("Remove episode-001")).click()
        page.wait_for_selector("text=Selected Files (1)")
        fi.set_input_files([str(EP1)])  # adding appends, does not replace
        page.wait_for_selector("text=Selected Files (2)")
        page.get_by_role("button", name=re.compile("Generate Beat-Aligned")).click()
        page.wait_for_selector("text=Promo Discovery Complete", timeout=30000)
        page.get_by_role("button", name=re.compile("Explore Generated Promos")).click()
        page.wait_for_selector("text=Showing only your uploads", timeout=5000)
        banner = page.inner_text("body")
        expect("episode-001" in banner and "episode-002" in banner, "both file chips")
        expect(re.search(r"Episodes:\s*2", page.inner_text("header")), "header shows 2 episodes")
        page.wait_for_selector("text=Candidate Leaderboard", timeout=10000)  # Explorer is lazy-loaded
        board = page.inner_text("body")
        expect("Episode 32" not in board.split("Candidate Leaderboard")[1][:3000], "pipeline clips must not be listed")
        expect("UNVERIFIED" in board, "uploaded clips are UNVERIFIED")
        # remove one uploaded file
        page.get_by_label(re.compile("Remove episode-001")).click()
        page.wait_for_timeout(300)
        expect("episode-001" not in page.inner_text("body").split("Showing only your uploads")[1][:400], "chip removed")
        # remove the last one -> back to pipeline results
        page.get_by_label(re.compile("Remove episode-002")).click()
        page.wait_for_selector("text=60 clips", timeout=5000)
        expect("Showing only your uploads" not in page.inner_text("body"), "banner gone")

    @step("9 upload view: restore button returns pipeline results")
    def _():
        tab("Overview")
        page.get_by_role("button", name=re.compile("Upload & Generate")).first.click()
        page.locator("input[type=file][accept*='.txt']").set_input_files([str(EP1)])
        page.get_by_role("button", name=re.compile("Generate Beat-Aligned")).click()
        page.wait_for_selector("text=Promo Discovery Complete", timeout=30000)
        page.get_by_role("button", name=re.compile("Explore Generated Promos")).click()
        page.wait_for_selector("text=Showing only your uploads")
        page.get_by_role("button", name=re.compile(r"Show pipeline results \(60\)")).click()
        page.wait_for_selector("text=60 clips")
        expect("Showing only your uploads" not in page.inner_text("body"), "banner gone")

    @step("9b home after an upload: continue banner; existing-results card still shows the saved 60")
    def _():
        tab("Overview")
        page.get_by_role("button", name=re.compile("Upload & Generate")).first.click()
        page.locator("input[type=file][accept*='.txt']").set_input_files([str(EP1)])
        page.get_by_role("button", name=re.compile("Generate Beat-Aligned")).click()
        page.wait_for_selector("text=Promo Discovery Complete", timeout=30000)
        page.get_by_role("button", name=re.compile("Explore Generated Promos")).click()
        page.wait_for_selector("text=Showing only your uploads")
        tab("Home")
        page.wait_for_selector("text=Continue with my uploads")
        expect("Showing only your uploads" not in page.inner_text("body"), "upload banner hidden on Home")
        card = page.get_by_role("button", name="Open existing results")
        expect("60" in card.inner_text() and "50" in card.inner_text(), "card shows saved pipeline stats: " + card.inner_text()[:120])
        page.get_by_role("button", name="Continue with my uploads").click()
        page.wait_for_selector("text=Showing only your uploads")
        tab("Home")
        card.click()  # restores the saved results
        page.wait_for_selector("text=60 clips", timeout=5000)
        expect("Showing only your uploads" not in page.inner_text("body"), "saved results restored")

    @step("10 batch AI: bad key stops after 1 call and opens settings")
    def _():
        page.evaluate("localStorage.setItem('kuku_gemini_api_key','bad-key'); localStorage.setItem('kuku_gemini_model','gemini-3.5-flash-lite')")
        calls = []
        page.route("**/generativelanguage.googleapis.com/**", lambda r: (calls.append(1), r.fulfill(
            status=400, content_type="application/json",
            body=json.dumps({"error": {"message": "API key not valid. Please pass a valid API key."}}))))
        tab("Promo Explorer")
        page.get_by_role("button", name=re.compile("Batch AI Top 5")).click()
        page.wait_for_selector("text=Stopped after 0 evaluated", timeout=10000)
        expect(len(calls) == 1, f"expected 1 API call, got {len(calls)}")
        page.wait_for_selector("text=Connect an AI model", timeout=3000)
        page.unroute("**/generativelanguage.googleapis.com/**")

    @step("11 batch AI: progress bar + cancel (mocked slow API)")
    def _():
        ok = {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "hook_score": 8, "cliffhanger_score": 8, "emotional_score": 8, "standalone_score": 8,
            "progression_score": 8, "is_promising": True})}]}}]}

        def slow(route):
            time.sleep(1.5)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(ok))

        page.keyboard.press("Escape")
        page.reload()
        page.wait_for_selector("header")
        page.route("**/generativelanguage.googleapis.com/**", slow)
        tab("Promo Explorer")
        page.get_by_role("button", name=re.compile("Batch AI Top 5")).click()
        page.wait_for_selector("text=AI evaluating", timeout=5000)
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_selector("text=Cancelled.", timeout=15000)
        expect(page.locator("text=AI evaluating").count() == 0, "progress bar hidden afterwards")
        page.unroute("**/generativelanguage.googleapis.com/**")

    @step("12 mobile-width layout does not overflow horizontally")
    def _():
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE)  # fresh load at Home
        page.wait_for_selector("text=Find the promos worth posting", state="attached", timeout=10000)
        sw = page.evaluate("document.documentElement.scrollWidth")
        expect(sw <= 400, f"page scrollWidth {sw} > viewport 390")

    @step("12b every tab fits a phone screen without sideways scrolling")
    def _():
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE)
        page.wait_for_selector("text=Find the promos worth posting", state="attached", timeout=10000)
        wide = []
        for label, marker in [
            ("Home", "Find the promos worth posting"),
            ("Overview", "Broken Soldier"),
            ("Promo Explorer", "Candidate Leaderboard"),
            ("Phone Simulator", "Previewing Vertical Promo"),
            ("Compare Battle", "Promo Comparison Battle"),
            ("Editorial Review", "Human Editorial Sign-Off"),
            ("Export NLE", "Export & NLE Delivery Station"),
        ]:
            tab(label)
            page.wait_for_selector(f"text={marker}", timeout=8000)
            page.wait_for_timeout(250)
            sw = page.evaluate("document.documentElement.scrollWidth")
            if sw > 395:
                wide.append((label, sw))
        expect(not wide, f"pages wider than the phone screen: {wide}")

    @step("12c header: fits narrow phones, keyboard works, active tab stays in view")
    def _():
        for w in (360, 320):
            page.set_viewport_size({"width": w, "height": 800})
            page.goto(BASE)
            page.wait_for_selector("header")
            page.wait_for_timeout(300)
            sw = page.evaluate("document.documentElement.scrollWidth")
            expect(sw <= w, f"header makes the page {sw}px wide on a {w}px screen")
            expect(page.get_by_role("button", name="Upload & Generate").count() == 1, "Upload keeps its accessible name")

        # keyboard: the logo is a real button; Enter takes you home
        page.set_viewport_size({"width": 390, "height": 800})
        page.goto(BASE)
        page.wait_for_selector("header")
        tab("Overview")
        page.wait_for_selector("text=Broken Soldier")
        page.get_by_role("button", name="Kuku Promo Studio home").focus()
        page.keyboard.press("Enter")
        page.wait_for_selector("text=Find the promos worth posting", timeout=5000)

        # the last tab must be scrolled into view on a phone, and marked as the current page
        tab("Export NLE")
        page.wait_for_selector("text=Export & NLE Delivery Station")
        page.wait_for_timeout(400)
        inside = page.evaluate(
            "() => { const n = document.querySelector('header nav'); const a = n.querySelector('[aria-current=page]');"
            " const nr = n.getBoundingClientRect(); const ar = a.getBoundingClientRect();"
            " return a.textContent.includes('Export NLE') && ar.left >= nr.left - 1 && ar.right <= nr.right + 1; }"
        )
        expect(inside, "active tab should be fully visible inside the scrolling tab row")
        page.set_viewport_size({"width": 1400, "height": 1000})

    @step("16 URL hash: Back button, refresh and deep links work")
    def _():
        page.set_viewport_size({"width": 1400, "height": 1000})
        page.goto(BASE)
        page.wait_for_selector("text=Find the promos worth posting")
        tab("Overview")
        page.wait_for_selector("text=Broken Soldier")
        expect(page.url.endswith("#/overview"), "URL follows the page: " + page.url)
        page.go_back()
        page.wait_for_selector("text=Find the promos worth posting", timeout=5000)
        page.go_forward()
        page.wait_for_selector("text=Broken Soldier", timeout=5000)
        page.goto(BASE + "#/explorer")                    # deep link
        page.wait_for_selector("text=Candidate Leaderboard", timeout=8000)
        page.reload()                                     # refresh keeps the page
        page.wait_for_selector("text=Candidate Leaderboard", timeout=8000)
        page.goto(BASE + "#/not-a-page")                  # unknown hash -> Home
        page.wait_for_selector("text=Find the promos worth posting", timeout=5000)

    @step("17 keyboard: leaderboard cards are buttons; arrow keys move the selection and the focus")
    def _():
        page.goto(BASE + "#/explorer")
        page.wait_for_selector("text=Candidate Leaderboard")
        cards = page.locator("button[data-cid]")
        cards.first.click()
        cards.first.focus()
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(250)
        expect(cards.nth(1).get_attribute("aria-pressed") == "true", "second card selected")
        second_id = cards.nth(1).get_attribute("data-cid")
        expect(page.evaluate("document.activeElement.getAttribute('data-cid')") == second_id, "focus follows the selection")
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(250)
        expect(cards.first.get_attribute("aria-pressed") == "true", "back on the first card")
        # Overview's top picks are real buttons too
        tab("Overview")
        page.wait_for_selector("text=Broken Soldier")
        page.get_by_role("button", name=re.compile(r"Rank #2")).click()
        page.wait_for_selector("text=Candidate Leaderboard")
        expect("Episode 24" in page.locator("button[data-cid][aria-pressed=true]").inner_text(), "opened the clicked pick")

    @step("18 hooks and cliffhangers do not get doubled quote marks")
    def _():
        page.goto(BASE + "#/explorer")
        page.wait_for_selector("text=Candidate Leaderboard")
        for i in range(0, 12):
            page.locator("button[data-cid]").nth(i).click()
            body = page.inner_text("body")
            expect('""' not in body and "\u201c\u201c" not in body, f"doubled quotes shown for card #{i + 1}")

    @step("19 empty data shows friendly pages, never NaN or a crash")
    def _():
        page.route("**/assets/promos-*.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body="export default [];"))
        page.goto(BASE)
        page.reload()                                     # fresh load so the empty data module is used
        page.wait_for_selector("text=No drama analysed yet", timeout=8000)
        for route, text in [("overview", "Nothing to show yet"), ("explorer", "No promos to explore"),
                            ("simulator", "No clip to preview"), ("compare", "Nothing to compare"),
                            ("review", "Nothing to review")]:
            page.goto(BASE + "#/" + route)
            page.wait_for_selector(f"text={text}", timeout=8000)
            expect("NaN" not in page.inner_text("body"), f"NaN shown on {route}")
        page.unroute("**/assets/promos-*.js")
        page.goto(BASE)
        page.reload()

    @step("20 upload: every file gets a result line, and failures are explained inline")
    def _():
        junk = SCRATCH / "junk.txt"
        junk.write_text("just some words, no timestamps at all", encoding="utf-8")
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        page.goto(BASE + "#/upload")
        page.wait_for_selector("text=Upload & Generate Promo Clips")
        fi = page.locator("input[type=file][accept*='.txt']")
        fi.set_input_files([str(EP1), str(junk)])
        page.get_by_role("button", name=re.compile("Generate Beat-Aligned")).click()
        page.wait_for_selector("text=Promo Discovery Complete", timeout=30000)
        report = page.get_by_label("File results").inner_text()
        expect("episode-001" in report and "promo" in report, "good file reported: " + report)
        expect("junk.txt" in report and "No promo windows" in report, "bad file explained: " + report)
        # only the bad file -> no promos at all: explained inline, not with a pop-up
        page.get_by_role("button", name="Upload Different Files").click()
        page.get_by_label(re.compile("Remove episode-001")).click()
        page.get_by_role("button", name=re.compile("Generate Beat-Aligned")).click()
        page.wait_for_selector("text=No promo windows were found", timeout=15000)
        expect(not dialogs, f"no browser alert expected, got {dialogs}")

    @step("21 review: A/R/N shortcuts save and advance, arrows move, typing in notes is safe")
    def _():
        page.goto(BASE + "#/review")
        page.evaluate("localStorage.removeItem('kuku_human_reviews')")
        page.reload()
        page.wait_for_selector("text=Human Editorial Sign-Off")
        sel = page.locator("select").first
        first_id = sel.input_value()
        page.keyboard.press("a")
        page.wait_for_selector("text=1 Approved")
        expect(sel.input_value() != first_id, "A should jump to the next unreviewed clip")
        expect("moved to the next unreviewed clip" in page.inner_text("body"), "shows what happened")
        page.keyboard.press("r")
        page.wait_for_selector("text=1 Rejected")
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
        label = sel.evaluate("e => e.options[e.selectedIndex].text")
        expect("Rank #2" in label and "[Rejected]" in label, "ArrowLeft goes back to the rejected clip: " + label)
        # typing letters in the notes box must not trigger shortcuts
        page.locator("textarea").click()
        page.keyboard.type("arn")
        page.wait_for_timeout(200)
        expect("2 Approved" not in page.inner_text("body") and "1 Approved" in page.inner_text("body"), "typing a/r/n in notes changed nothing")
        page.locator("textarea").fill("")
        page.get_by_role("button", name="Next unreviewed").click()
        page.wait_for_timeout(200)
        label = sel.evaluate("e => e.options[e.selectedIndex].text")
        expect("Rank #3" in label and "[" not in label, "Next unreviewed lands on a clip without a status: " + label)
        page.evaluate("localStorage.removeItem('kuku_human_reviews')")

    @step("22 explorer: copy buttons put the timecode, hook and cliffhanger on the clipboard")
    def _():
        page.goto(BASE + "#/explorer")
        page.reload()
        page.wait_for_selector("text=Candidate Leaderboard")
        page.locator("button[data-cid]").first.click()
        page.get_by_label("Copy timecode").click()
        page.wait_for_selector("text=Copied")
        text = page.evaluate("navigator.clipboard.readText()")
        expect(re.search(r"Episode \d+\s+\d\d:\d\d:\d\d:\d\d – \d\d:\d\d:\d\d:\d\d\s+\(", text), "timecode text: " + text)
        page.get_by_label("Copy hook").click()
        hook = page.evaluate("navigator.clipboard.readText()")
        expect(hook and not hook.startswith('"') and not hook.endswith('"'), "hook copied without wrapper quotes: " + hook)
        page.get_by_label("Copy cliffhanger").click()
        expect(page.evaluate("navigator.clipboard.readText()") != hook, "cliffhanger copied")

    @step("23 explorer: Compare opens the Compare page with this clip as A and the top pick as B")
    def _():
        page.goto(BASE + "#/explorer")
        page.wait_for_selector("text=Candidate Leaderboard")
        cards = page.locator("button[data-cid]")
        top_id, third_id = cards.nth(0).get_attribute("data-cid"), cards.nth(2).get_attribute("data-cid")
        cards.nth(2).click()
        page.get_by_role("button", name="Compare", exact=True).click()
        page.wait_for_selector("text=Promo Comparison Battle")
        expect(page.locator("select").nth(0).input_value() == third_id, "A is the clip we came from")
        expect(page.locator("select").nth(1).input_value() == top_id, "B is the top pick")
        # coming from the top pick itself, B becomes the runner-up
        page.goto(BASE + "#/explorer")
        page.wait_for_selector("text=Candidate Leaderboard")
        cards.nth(0).click()
        page.get_by_role("button", name="Compare", exact=True).click()
        page.wait_for_selector("text=Promo Comparison Battle")
        expect(page.locator("select").nth(0).input_value() == top_id, "A is the top pick")
        expect(page.locator("select").nth(1).input_value() != top_id, "B is another clip (the runner-up)")

    @step("24 explorer filters survive a refresh and can be reset; toasts can be dismissed")
    def _():
        page.goto(BASE + "#/explorer")
        page.wait_for_selector("text=Candidate Leaderboard")
        page.locator('select[aria-label="Compliance"]').select_option("PASS")
        page.locator('input[aria-label="Minimum score"]').fill("70")
        page.reload()
        page.wait_for_selector("text=Candidate Leaderboard")
        expect(page.locator('select[aria-label="Compliance"]').input_value() == "PASS", "compliance filter remembered")
        expect(page.locator('input[aria-label="Minimum score"]').input_value() == "70", "min score remembered")
        shown = int(re.search(r"Candidate Leaderboard \((\d+)\)", page.inner_text("body")).group(1))
        expect(0 < shown < 60, f"filters are applied after refresh ({shown} shown)")
        page.get_by_role("button", name="Reset filters").click()
        page.wait_for_selector("text=Candidate Leaderboard (60)")
        expect(page.get_by_role("button", name="Reset filters").count() == 0, "reset button gone when nothing is filtered")
        # toasts have a close button
        page.get_by_role("button", name=re.compile("AI Model")).click()
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_selector("text=AI model saved")
        page.get_by_role("button", name="Dismiss notification").click()
        expect(page.locator("text=AI model saved").count() == 0, "toast dismissed")

    @step("25 review: no preselected verdict, key auto-repeat, dialogs, scoped counts, import validation, a11y")
    def _():
        import json, tempfile, os
        page.goto(BASE + "#/review")
        page.evaluate("localStorage.removeItem('kuku_human_reviews')")
        page.reload()
        page.wait_for_selector("text=Human Editorial Sign-Off")
        expect(all(r.get_attribute("aria-checked") == "false" for r in page.get_by_role("radio").all()), "no verdict preselected")
        save = page.get_by_role("button", name="Save Review Decision")
        expect(save.is_disabled(), "Save disabled until a verdict is chosen")
        expect(page.get_by_label("Select Candidate for Review").count() == 1, "select has a label")
        expect(page.get_by_label(re.compile("Trimming")).count() == 1, "notes has a label")
        expect(page.get_by_text("Screenplay excerpt").count() > 0, "excerpt available")
        # holding a key down approves only one clip
        page.keyboard.down("a")
        for _i in range(5):
            page.keyboard.down("a")
        page.keyboard.up("a")
        page.wait_for_timeout(300)
        expect("1 Approved" in page.inner_text("body"), "auto-repeat approved exactly one")
        # shortcuts stand down behind a dialog
        page.get_by_role("button", name=re.compile("AI Model")).click()
        page.get_by_role("dialog").wait_for()
        page.get_by_role("button", name="Test connection").focus()
        page.keyboard.press("r")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        expect("1 Rejected" not in page.inner_text("body"), "R ignored while dialog open")
        # unsaved flag
        page.get_by_role("radio", name=re.compile("Reject Candidate")).click()
        expect(page.get_by_text("Unsaved changes").count() > 0, "unsaved flag shown")
        # invalid import is rejected
        bad = os.path.join(tempfile.mkdtemp(), "bad.json")
        open(bad, "w", encoding="utf-8").write(json.dumps({"reviews": {"x": {"status": "Banana"}}}))
        page.locator("input[type=file][accept*='json']").set_input_files(bad)
        page.wait_for_selector("text=Import failed")
        page.evaluate("localStorage.removeItem('kuku_human_reviews')")

    @step("13 header shows the model connected from .env (key never in the browser)")
    def _():
        page.set_viewport_size({"width": 1400, "height": 1000})
        page.evaluate("localStorage.clear()")
        page.goto(BASE)
        page.wait_for_selector("text=Find the promos worth posting", timeout=10000)
        dot = page.get_by_label("model connected")
        dot.wait_for(state="attached", timeout=10000)
        btn = page.get_by_role("button", name=re.compile("AI Model"))
        expect("gemini:" in (btn.get_attribute("title") or ""), "title names the connected model: " + str(btn.get_attribute("title")))
        expect(page.evaluate("Object.keys(localStorage).filter(k => /key/i.test(k)).length") == 0, "no key stored in the browser")

    @step("14 AI Model dialog: model name + key -> provider detected, test, save, back to .env")
    def _():
        hf_calls = []

        def hf(route):
            hf_calls.append(route.request.headers.get("authorization"))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"choices": [{"message": {"content": '{"status":"working"}'}}]}))

        page.route("**/router.huggingface.co/**", hf)
        page.get_by_role("button", name=re.compile("AI Model")).click()
        page.wait_for_selector("text=Connect an AI model")
        expect("Connected through the project" in page.inner_text("body"), "shows the .env connection")

        page.fill("#model-name", "meta-llama/Llama-3.1-8B-Instruct")
        page.fill("#api-key", "hf_testtoken123")
        expect("Hugging Face" in page.inner_text("body"), "Hugging Face detected from the key/model")
        page.get_by_role("button", name="Test connection").click()
        page.wait_for_selector("text=Connected to huggingface:meta-llama/Llama-3.1-8B-Instruct", timeout=8000)
        expect(hf_calls == ["Bearer hf_testtoken123"], f"request used the typed token: {hf_calls}")

        page.fill("#model-name", "gpt-4o-mini")
        page.fill("#api-key", "sk-testkey")
        expect("OpenAI" in page.inner_text("body"), "OpenAI detected")
        page.fill("#model-name", "claude-haiku-4-5")
        page.fill("#api-key", "sk-ant-testkey")
        expect("Anthropic Claude" in page.inner_text("body"), "Anthropic detected")

        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_selector("text=AI model saved: anthropic:claude-haiku-4-5")
        stored = page.evaluate("localStorage.getItem('kuku_gemini_model')")
        expect(stored == "claude-haiku-4-5", "model saved: " + str(stored))

        # clear everything -> falls back to the .env connection
        page.get_by_role("button", name=re.compile("AI Model")).click()
        page.get_by_role("button", name="Clear fields").click()
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_selector("text=from .env")
        expect(page.evaluate("localStorage.getItem('kuku_gemini_api_key')") is None, "own key removed")
        page.unroute("**/router.huggingface.co/**")

    if os.environ.get("UI_TEST_LIVE"):
        @step("15 LIVE: evaluate a clip through the .env connection (one real model call)")
        def _():
            page.evaluate("localStorage.clear()")
            page.goto(BASE)
            page.wait_for_selector("text=Find the promos worth posting", timeout=10000)
            tab("Promo Explorer")
            page.get_by_role("button", name=re.compile("Evaluate with AI")).first.click()
            page.wait_for_selector("text=AI evaluation complete", timeout=60000)

    browser.close()

print(f"\n==== UI TEST RESULTS (artifacts in {SCRATCH}) ====")
for name, ok, detail in results:
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "\n        " + detail))
bad = [e for e in console_errors if "generativelanguage" not in e and "Failed to load resource" not in e]
print(f"\nconsole/page errors (excluding the mocked API 400s): {len(bad)}")
for e in bad[:8]:
    print("  -", e[:200])
sys.exit(0 if all(r[1] for r in results) else 1)
