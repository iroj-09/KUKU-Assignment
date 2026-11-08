import React, { useState, useEffect, useRef, useCallback, Suspense, lazy } from 'react';
import Header from './components/Header';
const HomeTab = lazy(() => import('./components/HomeTab'));
const OverviewTab = lazy(() => import('./components/OverviewTab'));
const ExplorerTab = lazy(() => import('./components/ExplorerTab'));
const SimulatorTab = lazy(() => import('./components/SimulatorTab'));
const CompareTab = lazy(() => import('./components/CompareTab'));
const ReviewTab = lazy(() => import('./components/ReviewTab'));
const ExportTab = lazy(() => import('./components/ExportTab'));
import UploadModal from './components/UploadModal';
import ModelSettingsModal from './components/ModelSettingsModal';
import PageSkeleton from './components/Skeleton';
import { byScoreThenRank } from './utils/ranking';
import { loadUpload, saveUpload, clearUpload } from './utils/uploadStore';
import { X } from 'lucide-react';
import {
  evaluateCandidateWithGemini,
  evaluateBatchWithGemini,
  loadServerStatus,
  describeModel,
} from './utils/geminiEvaluator';

// The current page lives in the URL hash (#/explorer), so the browser's Back button, refresh and
// shared links all work.
const TABS = ['home', 'overview', 'explorer', 'simulator', 'compare', 'review', 'export', 'upload'];
function tabFromHash() {
  const t = window.location.hash.replace(/^#\/?/, '');
  return TABS.includes(t) ? t : 'home';
}

// Human reviews live in this browser's localStorage; read them once at start-up.
function loadReviews() {
  try {
    const saved = localStorage.getItem('kuku_human_reviews');
    return saved ? JSON.parse(saved) : {};
  } catch (e) {
    console.error('Failed to load reviews from localStorage', e);
    return {};
  }
}

export default function App() {
  const [compareSeed, setCompareSeed] = useState(null); // {a, b} clip ids from the Explorer's Compare button
  const [activeTab, setActiveTabState] = useState(tabFromHash);
  const setActiveTab = useCallback((tab) => {
    if (tab !== 'compare') setCompareSeed(null);
    setActiveTabState(tab);
    if (tabFromHash() !== tab) window.history.pushState(null, '', `#/${tab}`);
  }, []);
  useEffect(() => {
    const sync = () => setActiveTabState(tabFromHash());
    window.addEventListener('popstate', sync);
    window.addEventListener('hashchange', sync);
    return () => {
      window.removeEventListener('popstate', sync);
      window.removeEventListener('hashchange', sync);
    };
  }, []);
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [dataReady, setDataReady] = useState(false);
  // The app ships with no show data: every clip comes from the user's own uploaded screenplay files.
  const [uploadSource, setUploadSource] = useState(null); // filenames[] | null
  const [reviews, setReviews] = useState(loadReviews);
  const [isGeminiSettingsOpen, setIsGeminiSettingsOpen] = useState(false);
  const [modelLabel, setModelLabel] = useState(''); // e.g. "gemini:gemini-3.5-flash-lite", '' = none
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [notification, setNotification] = useState(null);
  const [batchProgress, setBatchProgress] = useState(null);
  const batchAbort = useRef(null);

  // Bring back the clips from the user's earlier upload (kept in this browser), so a refresh loses nothing.
  useEffect(() => {
    let cancelled = false;
    loadUpload()
      .then((saved) => {
        if (cancelled || !saved) return;
        setCandidates(saved.candidates);
        setSelectedCandidate(saved.candidates[0] || null);
        setUploadSource(saved.sources);
      })
      .finally(() => !cancelled && setDataReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep the uploaded clips (including AI re-ranking and removals) saved while they are showing.
  useEffect(() => {
    if (!dataReady) return;
    if (uploadSource) saveUpload(uploadSource, candidates);
    else clearUpload();
  }, [dataReady, uploadSource, candidates]);

  // Which model is connected? (the project's .env via the local proxy, or a key saved in this browser)
  useEffect(() => {
    loadServerStatus().finally(() => setModelLabel(describeModel()));
  }, []);

  const toastTimer = useRef(null);
  const showToast = (msg, isError = false) => {
    setNotification({ text: msg, isError });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setNotification(null), 6000);
  };

  const handleCompare = (candidate) => {
    const other = candidates.find((c) => c.rank === 1 && c.id !== candidate.id) || candidates.find((c) => c.id !== candidate.id);
    setCompareSeed({ a: candidate.id, b: other?.id });
    setActiveTab('compare');
  };

  const handleSelectCandidate = (candidate) => {
    setSelectedCandidate(candidate);
    setActiveTab('explorer');
  };

  const handleOpenSimulator = (candidate) => {
    setSelectedCandidate(candidate);
    setActiveTab('simulator');
  };

  const handleOpenReview = (candidate) => {
    setSelectedCandidate(candidate);
    setActiveTab('review');
  };

  const handlePromosGenerated = (newPromos, filenames) => {
    // A further upload adds to the clips already showing.
    const base = candidates;

    // Skip clips already present (same episode + bounds) so re-uploads don't duplicate ids.
    const existingIds = new Set(base.map((c) => c.id));
    const fresh = newPromos.filter((c) => !existingIds.has(c.id));
    const combined = [...fresh, ...base]
      .sort(byScoreThenRank)
      .map((c, idx) => ({ ...c, rank: idx + 1 }));
    setCandidates(combined);
    setSelectedCandidate(combined[0] || null);
    const allSources = [...new Set([...(uploadSource || []), ...filenames])];
    setUploadSource(allSources);
    setActiveTab('explorer');
    const skipped = newPromos.length - fresh.length;
    showToast(
      `Showing ${combined.length} candidate promos from ${allSources.join(', ')}` +
        (skipped ? ` (${skipped} duplicates skipped)` : '') + '.'
    );
  };

  // Remove every clip that came from one uploaded file.
  const handleRemoveUploadedFile = (filename) => {
    const remainingSources = (uploadSource || []).filter((n) => n !== filename);
    const remaining = candidates
      .filter((c) => c.sourceFile !== filename)
      .map((c, idx) => ({ ...c, rank: idx + 1 }));

    if (remainingSources.length === 0 || remaining.length === 0) {
      // Nothing uploaded is left: back to the upload page.
      setCandidates([]);
      setSelectedCandidate(null);
      setUploadSource(null);
      setActiveTab('upload');
      showToast(`Removed ${filename}. Upload a drama to continue.`);
      return;
    }

    setCandidates(remaining);
    setSelectedCandidate((cur) =>
      remaining.find((c) => c.id === cur?.id) || remaining[0] || null
    );
    setUploadSource(remainingSources);
    showToast(`Removed ${filename}.`);
  };

  // Live Single Gemini AI Evaluation Handler
  const handleEvaluateCandidate = async (candidateToEvaluate) => {
    if (!candidateToEvaluate) return;
    setIsEvaluating(true);
    showToast(`Evaluating ${candidateToEvaluate.episode} with AI...`);

    try {
      const updated = await evaluateCandidateWithGemini(candidateToEvaluate);

      const updatedList = candidates.map((c) => (c.id === updated.id ? updated : c));
      updatedList.sort(byScoreThenRank);
      const reranked = updatedList.map((c, idx) => ({ ...c, rank: idx + 1 }));

      setCandidates(reranked);
      setSelectedCandidate(reranked.find((c) => c.id === updated.id) || updated);
      showToast(`✨ AI evaluation complete! New Hybrid Score: ${updated.hybridScore}/100`);
    } catch (err) {
      console.error('Gemini evaluation error:', err);
      showToast(err.message || 'AI evaluation failed. Check your API key.', true);
      if (err.message && err.message.toLowerCase().includes('key')) {
        setIsGeminiSettingsOpen(true);
      }
    } finally {
      setIsEvaluating(false);
    }
  };

  // Batch Gemini AI Evaluation Handler
  const handleBatchEvaluate = async (candidatesToEval) => {
    if (!candidatesToEval || candidatesToEval.length === 0) return;
    setIsEvaluating(true);
    batchAbort.current = new AbortController();
    setBatchProgress({ curr: 0, total: candidatesToEval.length, label: '' });
    showToast(`Starting AI batch evaluation for ${candidatesToEval.length} candidates...`);

    try {
      const batch = await evaluateBatchWithGemini(
        candidatesToEval,
        undefined,
        undefined,
        (curr, total, cand) => {
          setBatchProgress({ curr, total, label: `${cand.episode} (${cand.clipStart}–${cand.clipEnd}s)` });
        },
        batchAbort.current.signal
      );

      const evalMap = new Map(batch.candidates.map((c) => [c.id, c]));
      const updatedList = candidates.map((c) => (evalMap.has(c.id) ? evalMap.get(c.id) : c));
      updatedList.sort(byScoreThenRank);
      const reranked = updatedList.map((c, idx) => ({ ...c, rank: idx + 1 }));

      setCandidates(reranked);
      setSelectedCandidate(reranked[0]);
      if (batch.cancelled) {
        showToast(`Cancelled. ${batch.evaluatedCount} evaluated before stopping.`);
      } else if (batch.abortReason) {
        showToast(
          `Stopped after ${batch.evaluatedCount} evaluated: ${batch.abortReason}`,
          true
        );
        if (batch.abortReason.toLowerCase().includes('key')) setIsGeminiSettingsOpen(true);
      } else if (batch.failed > 0) {
        showToast(`Evaluated ${batch.evaluatedCount}, ${batch.failed} failed (see console).`, true);
      } else {
        showToast(`✨ Batch AI evaluation complete! Re-ranked ${batch.evaluatedCount} candidates.`);
      }
    } catch (err) {
      console.error('Batch evaluation error:', err);
      showToast(err.message || 'Batch evaluation failed.', true);
    } finally {
      setIsEvaluating(false);
      setBatchProgress(null);
      batchAbort.current = null;
    }
  };

  const stats = {
    dramaName: 'Your uploads',
    totalCandidates: candidates.length,
    episodeCount: new Set(candidates.map((c) => c.episode)).size,
    topScore: candidates[0]?.hybridScore ?? 0,
    reviewedCount: candidates.filter((c) => reviews[c.id]).length, // only clips in this view
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-['Plus_Jakarta_Sans',sans-serif]">
      {/* Toast Notification */}
      {notification && (
        <div
          role={notification.isError ? 'alert' : 'status'}
          className={`fixed bottom-6 right-6 z-50 max-w-sm text-white text-xs font-semibold pl-4 pr-2 py-3 rounded-2xl shadow-xl flex items-start gap-2 animate-fadeIn ${
            notification.isError ? 'bg-rose-600 border border-rose-500' : 'bg-emerald-600 border border-emerald-500'
          }`}
        >
          <span className="min-w-0 break-words">{notification.text}</span>
          <button
            type="button"
            onClick={() => setNotification(null)}
            aria-label="Dismiss notification"
            className="shrink-0 rounded-lg p-1 text-white/80 hover:bg-white/15 hover:text-white"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Top Navbar */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        stats={stats}
        onOpenUploadModal={() => setActiveTab('upload')}
        onOpenGeminiSettings={() => setIsGeminiSettingsOpen(true)}
        modelLabel={modelLabel}
      />

      {/* Batch evaluation progress */}
      {batchProgress && (
        <div className="bg-amber-50 border-b border-amber-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex justify-between text-[11px] font-semibold text-amber-800 mb-1">
                <span className="truncate">
                  AI evaluating {Math.min(batchProgress.curr, batchProgress.total)}/{batchProgress.total}
                  {batchProgress.label ? ` · ${batchProgress.label}` : ''}
                </span>
              </div>
              <div className="h-1.5 bg-amber-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 transition-all"
                  style={{ width: `${(batchProgress.curr / Math.max(1, batchProgress.total)) * 100}%` }}
                />
              </div>
            </div>
            <button
              type="button"
              onClick={() => batchAbort.current?.abort()}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-amber-300 text-amber-800 text-[11px] font-semibold hover:bg-amber-100"
            >
              <X className="w-3 h-3" /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Upload view banner */}
      {uploadSource && activeTab !== 'home' && activeTab !== 'upload' && (
        <div className="bg-sky-50 border-b border-sky-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center gap-3 text-[11px] font-semibold text-sky-800">
            <div className="flex-1 min-w-0 flex flex-wrap items-center gap-1.5">
              <span>Promos from your uploads ({candidates.length}):</span>
              {uploadSource.map((name) => (
                <span
                  key={name}
                  className="inline-flex items-center gap-1 max-w-[16rem] pl-2 pr-1 py-0.5 rounded-full bg-white border border-sky-300"
                >
                  <span className="truncate">{name}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveUploadedFile(name)}
                    title={`Remove ${name}`}
                    aria-label={`Remove ${name}`}
                    className="p-0.5 rounded-full text-sky-500 hover:text-rose-600 hover:bg-rose-50"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Main Tab Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Suspense fallback={<PageSkeleton />}>
        {!dataReady ? (
          <PageSkeleton />
        ) : (
        <>
        {activeTab === 'home' && (
          <HomeTab
            upload={{ count: uploadSource ? candidates.length : 0, files: uploadSource || [] }}
            onOpenUpload={() => setActiveTab('upload')}
            onContinueUpload={() => setActiveTab('explorer')}
          />
        )}

        {activeTab === 'upload' && (
          <UploadModal
            asPage
            isOpen
            onClose={() => setActiveTab('home')}
            onPromosGenerated={handlePromosGenerated}
          />
        )}

        {activeTab === 'overview' && (
          <OverviewTab
            candidates={candidates}
            showTitle="Your uploaded scripts"
            onSelectCandidate={handleSelectCandidate}
            setActiveTab={setActiveTab}
          />
        )}

        {activeTab === 'explorer' && (
          <ExplorerTab
            candidates={candidates}
            selectedCandidate={selectedCandidate}
            onSelectCandidate={setSelectedCandidate}
            onOpenSimulator={handleOpenSimulator}
            onOpenReview={handleOpenReview}
            onCompare={handleCompare}
            onEvaluateCandidate={handleEvaluateCandidate}
            onBatchEvaluate={handleBatchEvaluate}
            isEvaluating={isEvaluating}
          />
        )}

        {activeTab === 'simulator' && (
          <SimulatorTab
            key={selectedCandidate?.id} // a different clip remounts the player, so it always starts at 0
            candidate={selectedCandidate}
            candidates={candidates}
            onSelectCandidate={setSelectedCandidate}
          />
        )}

        {activeTab === 'compare' && (
          <CompareTab
            candidates={candidates}
            seed={compareSeed}
          />
        )}

        {activeTab === 'review' && (
          <ReviewTab
            candidates={candidates}
            reviews={reviews}
            setReviews={setReviews}
            selectedCandidate={selectedCandidate}
            onOpenExplorer={handleSelectCandidate}
            onOpenSimulator={handleOpenSimulator}
          />
        )}

        {activeTab === 'export' && (
          <ExportTab
            candidates={candidates}
            reviews={reviews}
          />
        )}
        </>
        )}
        </Suspense>
      </main>

      {/* AI model connection dialog */}
      <ModelSettingsModal
        isOpen={isGeminiSettingsOpen}
        onClose={() => setIsGeminiSettingsOpen(false)}
        onSave={(label) => {
          setModelLabel(describeModel());
          showToast(label ? `AI model saved: ${label}` : 'AI model settings cleared.');
        }}
      />

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="font-medium text-slate-700">Kuku Promo Discovery Studio · AI Microdrama Editorial Intelligence</span>
          <span className="text-[11px] text-slate-500">Screenplay evidence analysis · 20–60s Promo Windows</span>
        </div>
      </footer>
    </div>
  );
}
