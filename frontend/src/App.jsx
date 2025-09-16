import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import Home from './pages/Home';
import FormPage from './pages/FormPage';
import Profile from './pages/Profile';
import AdminPdfs from './pages/AdminPdfs';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/form" element={<FormPage />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/admin/pdfs" element={<AdminPdfs />} />
      </Routes>
    </Router>
  );
}

export default App;
