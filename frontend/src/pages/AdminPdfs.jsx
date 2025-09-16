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
      <td><input value={v.group_key || ""} onChange={(e)=>onChange({ ...v, group_key: e.target.value })} /></td>
      <td><input value={v.bucket || ""} onChange={(e)=>onChange({ ...v, bucket: e.target.value })} /></td>
      <td><input value={v.path || ""} onChange={(e)=>onChange({ ...v, path: e.target.value })} /></td>
      <td><input value={v.label || ""} onChange={(e)=>onChange({ ...v, label: e.target.value })} /></td>
      <td><input type="number" value={v.order_index ?? 0} onChange={(e)=>onChange({ ...v, order_index: Number(e.target.value) })} style={{ width: 70 }} /></td>
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
  const [group, setGroup] = useState("profile");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newItem, setNewItem] = useState({ group_key: "profile", bucket: "", path: "", label: "", order_index: 0, is_default: false, score_min: null, score_max: null, active: true });
  const [editingId, setEditingId] = useState(null);
  const [editItem, setEditItem] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [upload, setUpload] = useState({ bucket: "", dest_path: "", label: "", order_index: 0, is_default: false, score_min: "", score_max: "", active: true, file: null });

  const adminPath = useMemo(() => `/api/admin/pdfs`, []);

  const load = async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${adminPath}?group=${encodeURIComponent(group)}`, { credentials: "same-origin" });
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

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [group]);

  // Admin gate: verify admin session on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/admin/me', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('not admin');
      } catch (e) {
        navigate('/');
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async () => {
    try {
      const res = await fetch(adminPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(newItem),
      });
      if (!res.ok) throw new Error(await res.text());
      setCreating(false);
      setNewItem({ group_key: group, bucket: "", path: "", label: "", order_index: 0, is_default: false, score_min: null, score_max: null, active: true });
      await load();
    } catch (e) {
      alert(`Create failed: ${e.message || e}`);
    }
  };

  const saveEdit = async (id) => {
    try {
      const res = await fetch(`${adminPath}/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(editItem),
      });
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
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (e) {
      alert(`Delete failed: ${e.message || e}`);
    }
  };

  return (
    <div style={{ padding: 16 }}>
      <h2>PDF Assets Admin</h2>
      <div style={{ marginBottom: 12, display: "flex", gap: 12, alignItems: "flex-end" }}>
        <Field label="Group">
          <input value={group} onChange={(e)=>setGroup(e.target.value)} placeholder="e.g., profile" />
        </Field>
        <button onClick={load}>Refresh</button>
      </div>

      {error ? <div style={{ color: "#b00", marginBottom: 12 }}>{error}</div> : null}

      <div style={{ marginBottom: 16 }}>
        <button onClick={() => setCreating((v) => !v)}>{creating ? "Close" : "New Item"}</button>
        {creating && (
          <div style={{ border: "1px solid #ddd", padding: 12, marginTop: 12 }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Field label="Group"><input value={newItem.group_key} onChange={(e)=>setNewItem({ ...newItem, group_key: e.target.value })} /></Field>
              <Field label="Bucket"><input value={newItem.bucket} onChange={(e)=>setNewItem({ ...newItem, bucket: e.target.value })} /></Field>
              <Field label="Path"><input value={newItem.path} onChange={(e)=>setNewItem({ ...newItem, path: e.target.value })} /></Field>
              <Field label="Label"><input value={newItem.label || ""} onChange={(e)=>setNewItem({ ...newItem, label: e.target.value })} /></Field>
              <Field label="Order"><input type="number" value={newItem.order_index ?? 0} onChange={(e)=>setNewItem({ ...newItem, order_index: Number(e.target.value) })} /></Field>
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
            <Field label="Bucket"><input value={upload.bucket} onChange={(e)=>setUpload({ ...upload, bucket: e.target.value })} placeholder="private bucket name" /></Field>
            <Field label="Dest Path / Prefix"><input value={upload.dest_path} onChange={(e)=>setUpload({ ...upload, dest_path: e.target.value })} placeholder="e.g., profile/default/ or profile/score-5/" /></Field>
            <Field label="Group"><input value={group} onChange={(e)=>setGroup(e.target.value)} /></Field>
            <Field label="Label"><input value={upload.label} onChange={(e)=>setUpload({ ...upload, label: e.target.value })} /></Field>
            <Field label="Order"><input type="number" value={upload.order_index ?? 0} onChange={(e)=>setUpload({ ...upload, order_index: Number(e.target.value) })} /></Field>
            <Field label="Default"><input type="checkbox" checked={!!upload.is_default} onChange={(e)=>setUpload({ ...upload, is_default: e.target.checked })} /></Field>
            <Field label="Score Min"><input type="number" value={upload.score_min} onChange={(e)=>setUpload({ ...upload, score_min: e.target.value })} /></Field>
            <Field label="Score Max"><input type="number" value={upload.score_max} onChange={(e)=>setUpload({ ...upload, score_max: e.target.value })} /></Field>
            <Field label="Active"><input type="checkbox" checked={upload.active !== false} onChange={(e)=>setUpload({ ...upload, active: e.target.checked })} /></Field>
            <Field label="File"><input type="file" accept="application/pdf" onChange={(e)=>setUpload({ ...upload, file: e.target.files?.[0] || null })} /></Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <button disabled={uploading} onClick={async ()=>{
              if (!upload.bucket || !upload.file) { alert('Bucket and file are required'); return; }
              setUploading(true);
              try {
                const fd = new FormData();
                fd.append('bucket', upload.bucket);
                fd.append('dest_path', upload.dest_path || '');
                fd.append('upsert', 'true');
                fd.append('group_key', group);
                if (upload.label) fd.append('label', upload.label);
                fd.append('order_index', String(upload.order_index ?? 0));
                fd.append('is_default', String(!!upload.is_default));
                if (upload.score_min !== '') fd.append('score_min', String(upload.score_min));
                if (upload.score_max !== '') fd.append('score_max', String(upload.score_max));
                fd.append('active', String(upload.active !== false));
                fd.append('file', upload.file);
                const res = await fetch('/api/admin/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
                if (!res.ok) throw new Error(await res.text());
                await load();
                alert('Uploaded successfully');
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
              <th>Group</th>
              <th>Bucket</th>
              <th>Path</th>
              <th>Label</th>
              <th>Order</th>
              <th>Default</th>
              <th>Score Min</th>
              <th>Score Max</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} style={{ textAlign: "center" }}>Loading…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={10} style={{ textAlign: "center" }}>No items</td></tr>
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
                  <td>{it.group_key}</td>
                  <td>{it.bucket}</td>
                  <td>{it.path}</td>
                  <td>{it.label}</td>
                  <td>{it.order_index}</td>
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
