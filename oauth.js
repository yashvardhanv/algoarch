// Google and GitHub OAuth 2.0 (authorization-code flow). The server is the only party that
// ever sees the provider's tokens; the browser just gets AlgoArch's own signed session token.
//
// Env: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET,
//      PUBLIC_URL (e.g. https://algoarch.example.com; defaults to the request's own origin).
// Tests point the provider endpoints at a mock with OAUTH_TEST_BASE.

const crypto = require('crypto');

function endpoints(provider) {
  const t = process.env.OAUTH_TEST_BASE;
  if (t) {
    return {
      auth: `${t}/${provider}/authorize`, token: `${t}/${provider}/token`,
      user: `${t}/${provider}/user`, emails: `${t}/${provider}/emails`
    };
  }
  if (provider === 'google') {
    return {
      auth: 'https://accounts.google.com/o/oauth2/v2/auth',
      token: 'https://oauth2.googleapis.com/token',
      user: 'https://openidconnect.googleapis.com/v1/userinfo'
    };
  }
  return {
    auth: 'https://github.com/login/oauth/authorize',
    token: 'https://github.com/login/oauth/access_token',
    user: 'https://api.github.com/user',
    emails: 'https://api.github.com/user/emails'
  };
}

function creds(provider) {
  const P = provider.toUpperCase();
  const id = process.env[`${P}_CLIENT_ID`];
  const secret = process.env[`${P}_CLIENT_SECRET`];
  return id && secret ? { id, secret } : null;
}

const PROVIDERS = ['google', 'github'];
const isProvider = (p) => PROVIDERS.includes(p);
const configured = () => ({ google: !!creds('google'), github: !!creds('github') });

function baseUrl(req) {
  if (process.env.PUBLIC_URL) return process.env.PUBLIC_URL.replace(/\/+$/, '');
  const proto = req.headers['x-forwarded-proto'] || 'http';
  return `${proto}://${req.headers.host}`;
}
const redirectUri = (req, provider) => `${baseUrl(req)}/api/auth/${provider}/callback`;

function authorizeUrl(req, provider, state) {
  const c = creds(provider);
  const q = new URLSearchParams({
    client_id: c.id, redirect_uri: redirectUri(req, provider), state, response_type: 'code'
  });
  if (provider === 'google') {
    q.set('scope', 'openid email profile');
    q.set('prompt', 'select_account');
  } else {
    q.set('scope', 'read:user user:email');
    q.delete('response_type');
  }
  return `${endpoints(provider).auth}?${q}`;
}

async function getJson(url, init) {
  const r = await fetch(url, init);
  const text = await r.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) { /* not json */ }
  if (!r.ok) throw new Error(`${url.split('?')[0]} responded ${r.status}`);
  return data || {};
}

// Exchange the code and return a verified identity: { email, name, avatar }.
async function fetchIdentity(req, provider, code) {
  const c = creds(provider);
  const ep = endpoints(provider);
  const body = new URLSearchParams({
    client_id: c.id, client_secret: c.secret, code,
    redirect_uri: redirectUri(req, provider), grant_type: 'authorization_code'
  });
  const tok = await getJson(ep.token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body
  });
  if (!tok.access_token) throw new Error('Provider did not return an access token');
  const auth = { Authorization: `Bearer ${tok.access_token}`, Accept: 'application/json', 'User-Agent': 'algoarch' };

  if (provider === 'google') {
    const u = await getJson(ep.user, { headers: auth });
    if (!u.email || u.email_verified !== true) throw new Error('Your Google email is not verified');
    return { email: u.email, name: u.name || u.email.split('@')[0], avatar: u.picture };
  }

  const u = await getJson(ep.user, { headers: auth });
  const emails = await getJson(ep.emails, { headers: auth });
  const list = Array.isArray(emails) ? emails : [];
  const pick = list.find(e => e.primary && e.verified) || list.find(e => e.verified);
  if (!pick) throw new Error('Your GitHub account has no verified email');
  return { email: pick.email, name: u.name || u.login || pick.email.split('@')[0], avatar: u.avatar_url };
}

const newNonce = () => crypto.randomBytes(16).toString('base64url');

module.exports = { isProvider, configured, authorizeUrl, fetchIdentity, newNonce, baseUrl };
