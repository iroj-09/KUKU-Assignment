import React from 'react';
import { UploadCloud, ArrowRight, Sparkles, Layers, CheckCircle2, CheckSquare } from 'lucide-react';

/**
 * Landing page. The app ships with no show data (the screenplays are confidential), so the one entry
 * point is: upload a drama's screenplay files and generate its promos.
 */
export default function HomeTab({ upload, onOpenUpload, onContinueUpload }) {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Hero */}
      <div className="text-center space-y-2 pt-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-50 border border-rose-200 text-[11px] font-semibold text-rose-700">
          <Sparkles className="w-3 h-3" /> AI promo discovery for microdramas
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">
          Find the promos worth posting
        </h1>
        <p className="text-sm text-slate-500 max-w-xl mx-auto">
          20–60 second clips with a hook in the first 3 seconds and a cliffhanger at the cut, ranked so you know
          which to post first. Upload a drama's screenplay files and try it yourself.
        </p>
      </div>

      {/* Continue banner when the user already uploaded something */}
      {upload.count > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl bg-sky-50 border border-sky-200 text-xs text-sky-900">
          <span>
            You have <strong>{upload.count} promos</strong> from your uploaded file{upload.files.length === 1 ? '' : 's'}{' '}
            <span className="text-sky-700">({upload.files.join(', ')})</span>.
          </span>
          <button
            type="button"
            onClick={onContinueUpload}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-sky-300 font-semibold hover:bg-sky-100"
          >
            Continue with my uploads <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* The one option */}
      <button
        type="button"
        onClick={onOpenUpload}
        aria-label="Upload and generate"
        className="group w-full flex flex-col text-left p-6 rounded-3xl border border-slate-200 bg-white shadow-xs transition-all hover:border-rose-300 hover:shadow-md hover:-translate-y-0.5 cursor-pointer"
      >
        <div className="flex items-center justify-between">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-md shadow-rose-500/20">
            <UploadCloud className="w-6 h-6 text-white" />
          </div>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
            Runs in your browser
          </span>
        </div>

        <div className="mt-4 text-[11px] font-bold uppercase tracking-wide text-rose-600">Start here</div>
        <h2 className="mt-0.5 text-xl font-extrabold text-slate-900 leading-snug">Upload a drama and generate promos</h2>
        <p className="mt-1 text-xs text-slate-500 leading-relaxed">
          Drop the screenplay or subtitle files (.txt, .srt, .fountain) of a drama. Promo windows are found in
          seconds with no API cost, and your AI model can judge the best few.
        </p>

        <ul className="mt-4 space-y-1.5 text-xs text-slate-600">
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Clips start and end on dialogue boundaries</li>
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Your files stay on this computer</li>
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Then explore, preview, compare, review and export</li>
        </ul>

        <div className="mt-5 self-start inline-flex items-center gap-1.5 text-sm font-bold text-rose-600">
          Upload & Generate
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </div>
      </button>

      {/* How it works */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
        {[
          { icon: Layers, title: '1 · Find', text: 'Every valid 20–60 s stretch is generated and filtered by cheap rules.' },
          { icon: Sparkles, title: '2 · Judge', text: 'A model finds the hook and cliffhanger inside the opening 3 s and closing 5 s.' },
          { icon: CheckSquare, title: '3 · Review & export', text: 'Approve clips, then export markers or an EDL for your editor.' },
        ].map(({ icon: Icon, title, text }) => (
          <div key={title} className="p-4 rounded-2xl bg-white/70 border border-slate-200">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-800">
              <Icon className="w-4 h-4 text-rose-500" /> {title}
            </div>
            <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
