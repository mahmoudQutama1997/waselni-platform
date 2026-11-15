function escapeCell(value) {
  const text = value == null ? '' : String(value);
  const safe = /^[\t\r ]*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function exportCsv(filename, columns, rows) {
  if (!rows.length) return false;
  const lines = [
    columns.map(column => escapeCell(column.label)).join(','),
    ...rows.map(row => columns.map(column => {
      const value = typeof column.value === 'function' ? column.value(row) : row[column.key];
      return escapeCell(value);
    }).join(',')),
  ];
  const blob = new Blob([`\uFEFF${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
}
