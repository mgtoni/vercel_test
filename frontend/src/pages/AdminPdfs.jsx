
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

function Field({ label, children }) {
  return (
    <label style={{ display: "block", marginBottom: 8 }}>
      <div style={{ fontSize: 12, color: "#555" }}>{label}</div>
      {children}
    </label>
  );
}

function RowEditor({ value, onChange, onSave, onCancel }) {
  const v = value || {};
  return (
    <tr>
      <td><input value={v.module || ""} onChange={(e)=>onChange({ ...v, module: e.target.value })} /></td>
      <td><input value={v.lesson || ""} onChange={(e)=>onChange({ ...v, lesson: e.target.value })} /></td>
      <td><input value={v.path || ""} onChange={(e)=>onChange({ ...v, path: e.target.value })} /></td>
      <td><input type="checkbox" checked={!!v.is_default} onChange={(e)=>onChange({ ...v, is_default: e.target.checked })} /></td>
      <td><input type="number" value={v.score_min ?? ""} onChange={(e)=>onChange({ ...v, score_min: e.target.value === '' ? null : Number(e.target.value) })} style={{ width: 70 }} /></td>
      <td><input type="number" value={v.score_max ?? ""} onChange={(e)=>onChange({ ...v, score_max: e.target.value === '' ? null : Number(e.target.value) })} style={{ width: 70 }} /></td>
      <td><input type="checkbox" checked={v.active !== false} onChange={(e)=>onChange({ ...v, active: e.target.checked })} /></td>
      <td>
        <button onClick={onSave} style={{ marginRight: 6 }}>Save</button>
        <button onClick={onCancel}>Cancel</button>
      </td>
    </tr>
  );
}

export default function AdminPdfs() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [moduleFilter, setModuleFilter] = useState("");
  const [lessonFilter, setLessonFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const createEmptyItem = (moduleVal = "", lessonVal = "") => ({ module: moduleVal, lesson: lessonVal, path: "", is_default: false, score_min: null, score_max: null, active: true });
  const [newItem, setNewItem] = useState(createEmptyItem());
  const [editingId, setEditingId] = useState(null);
  const [editItem, setEditItem] = useState(null);
  const [uploading, setUploading] = useState(false);
  const createEmptyUpload = (moduleVal = "", lessonVal = "") => ({ module: moduleVal, lesson: lessonVal, is_default: false, score_min: "", score_max: "", active: true, file: null });
  const [upload, setUpload] = useState(createEmptyUpload());
  const [adminEmail, setAdminEmail] = useState("");

  const adminPath = useMemo(() => `/api/admin/pdfs`, []);

  const load = async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams();
      if (moduleFilter.trim()) params.set("module", moduleFilter.trim());
      if (lessonFilter.trim()) params.set("lesson", lessonFilter.trim());
      const qs = params.toString();
      const res = await fetch(qs ? `${adminPath}?${qs}` : adminPath, { credentials: "same-origin" });
      if (res.status === 401 || res.status === 403) {
        navigate('/admin/login', { replace: true });
        return;
      }
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items || []);
    } catch (e) {
      setError(`Load failed: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/admin/logout', { method: 'POST', credentials: 'same-origin' });
    } catch (err) {
      console.warn('Admin logout request failed', err);
    } finally {
      navigate('/admin/login', { replace: true });
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [moduleFilter, lessonFilter]);

  // Admin gate: verify admin session on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/admin/me', { credentials: 'same-origin' });
        if (res.status === 200) {
          const data = await res.json().catch(() => ({}));
          setAdminEmail(data?.email || "");
          return;
        }
        navigate('/admin/login', { replace: true });
      } catch (e) {
        navigate('/admin/login', { replace: true });
      }
    })();
// eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetNewItem = () => setNewItem(createEmptyItem(moduleFilter.trim(), lessonFilter.trim()));
  const resetUpload = () => setUpload(createEmptyUpload(moduleFilter.trim(), lessonFilter.trim()));

  const create = async () => {
    const trimmedModule = (newItem.module || '').trim();
    const trimmedPath = (newItem.path || '').trim();
    if (!trimmedModule || !trimmedPath) {
      alert('Module and path are required');
      return;
    }
    try {
      const payload = {
        module: trimmedModule,
        lesson: (newItem.lesson || '').trim() || null,
        path: trimmedPath,
        is_default: !!newItem.is_default,
        score_min: newItem.score_min === null ? null : Number(newItem.score_min),
        score_max: newItem.score_max === null ? null : Number(newItem.score_max),
        active: newItem.active !== false,
      };
      const res = await fetch(adminPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (res.status === 401 || res.status === 403) {
        navigate('/admin/login', { replace: true });
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      setCreating(false);
      resetNewItem();
      await load();
    } catch (e) {
      alert(`Create failed: ${e.message || e}`);
    }
  };

  const saveEdit = async (id) => {
    if (!editItem) return;
    const trimmedModule = (editItem.module || '').trim();
    const trimmedPath = (editItem.path || '').trim();
    if (!trimmedModule || !trimmedPath) {
      alert('Module and path are required');
      return;
    }
    const payload = {
      module: trimmedModule,
      lesson: (editItem.lesson || '').trim() || null,
      path: trimmedPath,
      is_default: !!editItem.is_default,
      score_min: editItem.score_min === null ? null : Number(editItem.score_min),
      score_max: editItem.score_max === null ? null : Number(editItem.score_max),
      active: editItem.active !== false,
    };
    try {
      const res = await fetch(`${adminPath}/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (res.status === 401 || res.status === 403) {
        navigate('/admin/login', { replace: true });
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      setEditingId(null);
      setEditItem(null);
      await load();
    } catch (e) {
      alert(`Update failed: ${e.message || e}`);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this item?")) return;
    try {
      const res = await fetch(`${adminPath}/${id}`, { method: "DELETE", credentials: "same-origin" });
      if (res.status === 401 || res.status === 403) {
        navigate('/admin/login', { replace: true });
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (e) {
      alert(`Delete failed: ${e.message || e}`);
    }
  };

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2>PDF Assets Admin</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {adminEmail ? <span style={{ fontSize: 14, color: "#444" }}>Signed in as {adminEmail}</span> : null}
          <button onClick={handleLogout}>Log out</button>
        </div>
      </div>
      <div style={{ marginBottom: 12, display: "flex", gap: 12, alignItems: "flex-end" }}>
        <Field label="Module">
          <input value={moduleFilter} onChange={(e)=>setModuleFilter(e.target.value)} placeholder="e.g., module-1" />
        </Field>
        <Field label="Lesson">
          <input value={lessonFilter} onChange={(e)=>setLessonFilter(e.target.value)} placeholder="optional lesson prefix" />
        </Field>
        <button onClick={load}>Refresh</button>
      </div>

      {error ? <div style={{ color: "#b00", marginBottom: 12 }}>{error}</div> : null}

      <div style={{ marginBottom: 16 }}>
        <button onClick={() => { const next = !creating; setCreating(next); if (next) resetNewItem(); }}>{creating ? "Close" : "New Item"}</button>
        {creating && (
          <div style={{ border: "1px solid #ddd", padding: 12, marginTop: 12 }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Field label="Module"><input value={newItem.module} onChange={(e)=>setNewItem({ ...newItem, module: e.target.value })} /></Field>
              <Field label="Lesson"><input value={newItem.lesson || ""} onChange={(e)=>setNewItem({ ...newItem, lesson: e.target.value })} placeholder="optional" /></Field>
              <Field label="Path"><input value={newItem.path} onChange={(e)=>setNewItem({ ...newItem, path: e.target.value })} placeholder="storage path incl. filename" /></Field>
              <Field label="Default"><input type="checkbox" checked={!!newItem.is_default} onChange={(e)=>setNewItem({ ...newItem, is_default: e.target.checked })} /></Field>
              <Field label="Score Min"><input type="number" value={newItem.score_min ?? ""} onChange={(e)=>setNewItem({ ...newItem, score_min: e.target.value === '' ? null : Number(e.target.value) })} /></Field>
              <Field label="Score Max"><input type="number" value={newItem.score_max ?? ""} onChange={(e)=>setNewItem({ ...newItem, score_max: e.target.value === '' ? null : Number(e.target.value) })} /></Field>
              <Field label="Active"><input type="checkbox" checked={newItem.active !== false} onChange={(e)=>setNewItem({ ...newItem, active: e.target.checked })} /></Field>
            </div>
            <div style={{ marginTop: 12 }}>
              <button onClick={create} style={{ marginRight: 8 }}>Create</button>
              <button onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        <h3>Upload PDF to Storage + Create Manifest</h3>
        <div style={{ border: "1px solid #ddd", padding: 12, marginTop: 12 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Field label="Module"><input value={upload.module} onChange={(e)=>setUpload({ ...upload, module: e.target.value })} placeholder="storage bucket" /></Field>
            <Field label="Lesson"><input value={upload.lesson} onChange={(e)=>setUpload({ ...upload, lesson: e.target.value })} placeholder="e.g., lesson-1/" /></Field>
            <Field label="Default"><input type="checkbox" checked={!!upload.is_default} onChange={(e)=>setUpload({ ...upload, is_default: e.target.checked })} /></Field>
            <Field label="Score Min"><input type="number" value={upload.score_min} onChange={(e)=>setUpload({ ...upload, score_min: e.target.value })} /></Field>
            <Field label="Score Max"><input type="number" value={upload.score_max} onChange={(e)=>setUpload({ ...upload, score_max: e.target.value })} /></Field>
            <Field label="Active"><input type="checkbox" checked={upload.active !== false} onChange={(e)=>setUpload({ ...upload, active: e.target.checked })} /></Field>
            <Field label="File"><input type="file" accept="application/pdf" onChange={(e)=>setUpload({ ...upload, file: e.target.files?.[0] || null })} /></Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <button disabled={uploading} onClick={async ()=>{
              const moduleValue = (upload.module || moduleFilter).trim();
              if (!moduleValue || !upload.file) { alert('Module and file are required'); return; }
              setUploading(true);
              try {
                const prep = new FormData();
                prep.append('module', moduleValue);
                prep.append('lesson', (upload.lesson || lessonFilter || '').trim());
                prep.append('filename', upload.file.name);
                const up = await fetch('/api/admin/upload-url', { method: 'POST', body: prep, credentials: 'same-origin' });
                if (up.status === 401 || up.status === 403) {
                  navigate('/admin/login', { replace: true });
                  return;
                }
                if (!up.ok) throw new Error(await up.text());
                const upData = await up.json();

                const putRes = await fetch(upData.signed_url, {
                  method: 'PUT',
                  headers: { 'Content-Type': upload.file.type || 'application/pdf' },
                  body: upload.file,
                });
                if (!putRes.ok) throw new Error(`Upload to storage failed: ${putRes.status}`);

                const manifest = {
                  module: upData.module || moduleValue,
                  lesson: (upload.lesson || lessonFilter || '').trim() || null,
                  path: upData.path,
                  is_default: !!upload.is_default,
                  score_min: upload.score_min === '' ? null : Number(upload.score_min),
                  score_max: upload.score_max === '' ? null : Number(upload.score_max),
                  active: upload.active !== false,
                };
                const manRes = await fetch('/api/admin/pdfs', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  credentials: 'same-origin',
                  body: JSON.stringify(manifest),
                });
                if (manRes.status === 401 || manRes.status === 403) {
                  navigate('/admin/login', { replace: true });
                  return;
                }
                if (!manRes.ok) throw new Error(await manRes.text());

                await load();
                alert('Uploaded successfully');
                resetUpload();
              } catch (e) {
                alert(`Upload failed: ${e.message || e}`);
              } finally {
                setUploading(false);
              }
            }}>Upload</button>
          </div>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th>Module</th>
              <th>Lesson</th>
              <th>Path</th>
              <th>Default</th>
              <th>Score Min</th>
              <th>Score Max</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: "center" }}>Loading...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: "center" }}>No items</td></tr>
            ) : items.map((it) => (
              editingId === it.id ? (
                <RowEditor
                  key={it.id}
                  value={editItem}
                  onChange={setEditItem}
                  onSave={() => saveEdit(it.id)}
                  onCancel={() => { setEditingId(null); setEditItem(null); }}
                />
              ) : (
                <tr key={it.id}>
                  <td>{it.module}</td>
                  <td>{it.lesson || ''}</td>
                  <td>{it.path}</td>
                  <td>{it.is_default ? "Yes" : "No"}</td>
                  <td>{it.score_min ?? ""}</td>
                  <td>{it.score_max ?? ""}</td>
                  <td>{it.active ? "Yes" : "No"}</td>
                  <td>
                    <button style={{ marginRight: 6 }} onClick={() => { setEditingId(it.id); setEditItem({ ...it }); }}>Edit</button>
                    <button onClick={() => remove(it.id)}>Delete</button>
                  </td>
                </tr>
              )
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
