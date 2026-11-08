// Order clips best score first. Equal scores keep the order the clip already had (its saved rank), so the
// pipeline's own tie-breaking survives; clips without a rank keep their input order (Array.sort is stable).
const NO_RANK = 1e9;
export const byScoreThenRank = (a, b) => b.hybridScore - a.hybridScore || (a.rank ?? NO_RANK) - (b.rank ?? NO_RANK);
