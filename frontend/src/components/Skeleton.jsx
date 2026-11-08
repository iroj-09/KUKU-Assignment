import React from 'react';

/** Placeholder shown while a page (or the promo data) is loading, instead of a bare "Loading…". */
export default function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <div className="h-40 animate-pulse rounded-2xl bg-slate-200/70" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-200/70" />
        ))}
      </div>
      <div className="h-56 animate-pulse rounded-2xl bg-slate-200/70" />
    </div>
  );
}
