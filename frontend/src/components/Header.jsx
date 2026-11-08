import React, { useEffect, useRef, useState } from 'react';
import { Home, Film, Sparkles, Layers, CheckSquare, Download, SplitSquareVertical, UploadCloud, Key, Smartphone } from 'lucide-react';

export default function Header({
  activeTab,
  setActiveTab,
  stats,
  onOpenUploadModal,
  onOpenGeminiSettings,
  modelLabel = '',
}) {
  const navItems = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'overview', label: 'Overview', icon: Layers },
    { id: 'explorer', label: 'Promo Explorer', icon: Film },
    { id: 'simulator', label: 'Phone Simulator', icon: Smartphone },
    { id: 'compare', label: 'Compare Battle', icon: SplitSquareVertical },
    { id: 'review', label: 'Editorial Review', icon: CheckSquare, badge: stats.reviewedCount },
    { id: 'export', label: 'Export NLE', icon: Download },
  ];

  // The tab row scrolls sideways on narrow screens. Fade its right edge while there is more to
  // reveal, and keep the active tab in view when it changes.
  const navRef = useRef(null);
  const [moreRight, setMoreRight] = useState(false);
  const measureNav = () => {
    const el = navRef.current;
    if (el) setMoreRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  };
  useEffect(() => {
    const el = navRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(measureNav); // also fires once on observe, giving the first measurement
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    navRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [activeTab]);

  return (
    <header className="border-b border-slate-200 bg-white/95 backdrop-blur sticky top-0 z-50 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Branding */}
          <button
            type="button"
            onClick={() => setActiveTab('home')}
            aria-label="Kuku Promo Studio home"
            className="flex min-w-0 items-center space-x-2.5 text-left sm:space-x-3"
          >
            <div className="w-9 h-9 sm:w-10 sm:h-10 shrink-0 rounded-xl bg-gradient-to-tr from-rose-600 via-rose-500 to-amber-500 flex items-center justify-center shadow-md shadow-rose-500/20">
              <Film className="w-5 h-5 text-white" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2">
                <span className="truncate font-extrabold text-sm sm:text-lg tracking-tight text-slate-900">
                  KUKU PROMO STUDIO
                </span>
                <span className="hidden xl:flex px-2 py-0.5 text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200 rounded-full items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5 text-rose-600" /> AI Discovery
                </span>
              </div>
              <p className="hidden sm:block truncate text-xs text-slate-500">Microdrama 20–60s Promo Intelligence</p>
            </div>
          </button>

          {/* Global Stats & Action CTAs */}
          <div className="flex shrink-0 items-center space-x-2 sm:space-x-3 pl-2">
            {/* Numbers describe the drama being viewed, so they appear on its pages only, not on Home/Upload
                where nothing has been chosen yet. */}
            {activeTab !== 'home' && activeTab !== 'upload' && (
            <div className="hidden xl:flex items-center space-x-6 text-xs mr-2">
              <div className="text-right">
                <span className="text-slate-500">Episodes: </span>
                <span className="font-bold text-slate-900">{stats.episodeCount}</span>
              </div>
              <div className="w-px h-6 bg-slate-200" />
              <div className="text-right">
                <span className="text-slate-500">Shortlisted: </span>
                <span className="font-bold text-rose-600">{stats.totalCandidates} clips</span>
              </div>
              <div className="w-px h-6 bg-slate-200" />
              <div className="text-right">
                <span className="text-slate-500">Top Hybrid Score: </span>
                <span className="font-bold text-emerald-600">{stats.topScore}/100</span>
              </div>
            </div>
            )}

            {/* AI model connection */}
            <button
              onClick={onOpenGeminiSettings}
              title={modelLabel ? `Connected: ${modelLabel}. Click to change the model or API key.` : 'Connect an AI model (model name + API key)'}
              className="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 text-xs font-semibold shadow-xs transition-all hover:scale-[1.02]"
            >
              <Key className="w-3.5 h-3.5 text-amber-600" />
              <span className="hidden sm:inline">AI Model</span>
              <span
                aria-label={modelLabel ? 'model connected' : 'no model connected'}
                className={`w-1.5 h-1.5 rounded-full ${modelLabel ? 'bg-emerald-500' : 'bg-slate-300'}`}
              />
            </button>

            {/* Launch Upload Modal Button */}
            <button
              onClick={onOpenUploadModal}
              title="Upload & Generate"
              className="inline-flex items-center gap-2 px-3 sm:px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-md shadow-rose-600/20 transition-all hover:scale-[1.02]"
            >
              <UploadCloud className="w-4 h-4" />
              <span className="sr-only whitespace-nowrap sm:not-sr-only">Upload & Generate</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <nav
          ref={navRef}
          aria-label="Main"
          onScroll={measureNav}
          className={`flex space-x-1 sm:space-x-2 overflow-x-auto py-2 border-t border-slate-100 no-scrollbar ${
            moreRight ? '[mask-image:linear-gradient(to_right,#000_calc(100%-32px),transparent)]' : ''
          }`}
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveTab(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-rose-50 text-rose-700 border border-rose-200 shadow-xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-rose-600' : 'text-slate-400'}`} />
                <span>{item.label}</span>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.2 bg-emerald-100 text-emerald-800 text-[10px] font-bold rounded-full border border-emerald-200">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
