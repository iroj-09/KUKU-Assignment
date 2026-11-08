import React from 'react';

/** Friendly placeholder for pages that have nothing to show yet. */
export default function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center shadow-xs">
      {Icon && (
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-500">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      )}
      <h2 className="text-base font-bold text-slate-900">{title}</h2>
      {children && <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
