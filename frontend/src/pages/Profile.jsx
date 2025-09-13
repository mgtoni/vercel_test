import React, { useEffect, useState } from 'react';

function Profile() {
  const [name, setName] = useState('');

  useEffect(() => {
    try {
      const raw = localStorage.getItem('auth_profile');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed.name === 'string') {
          setName(parsed.name);
        }
      }
    } catch {}
  }, []);

  return (
    <div>
      <h1>{`Welcome ${name || ''}`.trim()}</h1>
    </div>
  );
}

export default Profile;

