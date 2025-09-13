import React from 'react';
import { Link } from 'react-router-dom';

function Home() {
  return (
    <div>
      <h1>Home Page</h1>
      <div style={{ display: 'flex', gap: '1rem' }}>
        <Link to="/form">Go to Form</Link>
        <Link to="/profile">Go to Profile</Link>
      </div>
    </div>
  );
}

export default Home;
