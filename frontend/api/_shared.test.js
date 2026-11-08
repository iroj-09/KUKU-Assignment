import { describe, it, expect } from 'vitest';
import { allowCall, sameOrigin, MAX_CALLS_PER_WINDOW } from './_shared.js';

const req = (ip, headers = {}) => ({ headers: { host: 'app.example', 'x-forwarded-for': ip, ...headers }, socket: {} });

describe('deployed model proxy guards', () => {
  it('limits calls per visitor, and counts each visitor separately', () => {
    const now = Date.now();
    for (let i = 0; i < MAX_CALLS_PER_WINDOW; i += 1) expect(allowCall(req('9.9.9.9'), now)).toBe(true);
    expect(allowCall(req('9.9.9.9'), now)).toBe(false);
    expect(allowCall(req('8.8.8.8'), now)).toBe(true);
  });

  it('lets a visitor back in after the window passes', () => {
    const now = Date.now();
    for (let i = 0; i < MAX_CALLS_PER_WINDOW; i += 1) allowCall(req('7.7.7.7'), now);
    expect(allowCall(req('7.7.7.7'), now)).toBe(false);
    expect(allowCall(req('7.7.7.7'), now + 61 * 60 * 1000)).toBe(true);
  });

  it('only accepts requests from the app itself', () => {
    expect(sameOrigin(req('1.1.1.1'))).toBe(true); // no Origin header
    expect(sameOrigin(req('1.1.1.1', { origin: 'https://app.example' }))).toBe(true);
    expect(sameOrigin(req('1.1.1.1', { origin: 'https://evil.example' }))).toBe(false);
    expect(sameOrigin(req('1.1.1.1', { origin: 'not a url' }))).toBe(false);
  });
});
