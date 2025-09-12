import React, { useState } from 'react';

function Form() {
  // Existing form state
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  // Auth state
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'signup'
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authResult, setAuthResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const response = await fetch('/api/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, email }),
    });
    const data = await response.json();
    console.log(data);
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: authMode,
          email: authEmail,
          password: authPassword,
          name: authMode === 'signup' ? authName : undefined,
        }),
      });
      const data = await response.json();
      setAuthResult(data);
      console.log('Auth response:', data);
    } catch (err) {
      console.error('Auth error:', err);
      setAuthResult({ error: 'Request failed' });
    }
  };

  return (
    <div>
      <section style={{ marginBottom: '2rem', padding: '1rem', border: '1px solid #ccc' }}>
        <h2>Account</h2>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <button
            type="button"
            onClick={() => setAuthMode('login')}
            style={{
              padding: '0.5rem 1rem',
              background: authMode === 'login' ? '#333' : '#eee',
              color: authMode === 'login' ? '#fff' : '#000',
              border: '1px solid #333',
              cursor: 'pointer',
            }}
          >
            Log In
          </button>
          <button
            type="button"
            onClick={() => setAuthMode('signup')}
            style={{
              padding: '0.5rem 1rem',
              background: authMode === 'signup' ? '#333' : '#eee',
              color: authMode === 'signup' ? '#fff' : '#000',
              border: '1px solid #333',
              cursor: 'pointer',
            }}
          >
            Create Account
          </button>
        </div>

        <form onSubmit={handleAuthSubmit}>
          {authMode === 'signup' && (
            <div style={{ marginBottom: '0.5rem' }}>
              <label htmlFor="auth-name">Name:</label>
              <input
                type="text"
                id="auth-name"
                value={authName}
                onChange={(e) => setAuthName(e.target.value)}
                style={{ marginLeft: '0.5rem' }}
              />
            </div>
          )}
          <div style={{ marginBottom: '0.5rem' }}>
            <label htmlFor="auth-email">Email:</label>
            <input
              type="email"
              id="auth-email"
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
              style={{ marginLeft: '0.5rem' }}
              required
            />
          </div>
          <div style={{ marginBottom: '0.5rem' }}>
            <label htmlFor="auth-password">Password:</label>
            <input
              type="password"
              id="auth-password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              style={{ marginLeft: '0.5rem' }}
              required
            />
          </div>
          <button type="submit">{authMode === 'login' ? 'Log In' : 'Create Account'}</button>
        </form>
        {authResult && (
          <pre style={{ marginTop: '0.5rem', background: '#f7f7f7', padding: '0.5rem' }}>
{JSON.stringify(authResult, null, 2)}
          </pre>
        )}
      </section>

      <form onSubmit={handleSubmit}>
        <h2>Sample Form</h2>
        <div>
          <label htmlFor="name">Name:</label>
          <input
            type="text"
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="email">Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <button type="submit">Submit</button>
      </form>
    </div>
  );
}

export default Form;
