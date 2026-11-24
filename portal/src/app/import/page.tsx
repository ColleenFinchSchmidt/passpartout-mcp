"use client";

import React, { useState, useCallback, useRef } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";
import {
  Upload,
  FileSpreadsheet,
  FileText,
  ArrowLeft,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Users,
  BedDouble,
  BarChart3,
  DollarSign,
  Gift,
  Building,
  X,
  History,
  Trash2,
  Pencil,
  ChevronDown,
  Shield,
} from "lucide-react";

const ACCEPTED_TYPES = [
  ".xlsx", ".xls", ".csv", ".docx", ".pdf", ".txt",
];
const MAX_SIZE = 10 * 1024 * 1024;

type DataCategory = "rooms" | "occupancy" | "rates" | "guests" | "amenities" | "extras";

type Problem = {
  message: string;
  count?: number;
};

type ExtractedSection = {
  category: DataCategory;
  rows: Record<string, unknown>[];
  columns: string[];
  mappings: Record<string, string>;
  problems: Problem[];
};

type ParseResult = {
  fileName: string;
  sections: ExtractedSection[];
  problems: Problem[];
  cost_usd: number;
};

type ImportRecord = {
  id: string;
  fileName: string;
  importedAt: string;
  categories: DataCategory[];
  rowCounts: Record<string, number>;
};

const categoryIcons: Record<DataCategory, React.ReactNode> = {
  rooms: <BedDouble className="w-4 h-4" />,
  occupancy: <BarChart3 className="w-4 h-4" />,
  rates: <DollarSign className="w-4 h-4" />,
  guests: <Users className="w-4 h-4" />,
  amenities: <Building className="w-4 h-4" />,
  extras: <Gift className="w-4 h-4" />,
};

export default function ImportPage() {
  const { locale } = useLocale();
  const labels = t(locale).import;

  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ParseResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [history, setHistory] = useState<ImportRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [editingMapping, setEditingMapping] = useState<{section: number; orig: string} | null>(null);
  const [editedMappings, setEditedMappings] = useState<Record<number, Record<string, string>>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  const categoryLabel = useCallback((cat: DataCategory) => {
    return labels[cat] || cat;
  }, [labels]);

  const getMappedName = useCallback((sectionIdx: number, orig: string, defaultMapped: string) => {
    return editedMappings[sectionIdx]?.[orig] ?? defaultMapped;
  }, [editedMappings]);

  const setMappedName = useCallback((sectionIdx: number, orig: string, newName: string) => {
    setEditedMappings(prev => ({
      ...prev,
      [sectionIdx]: { ...prev[sectionIdx], [orig]: newName },
    }));
    setEditingMapping(null);
  }, []);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const file = files[0];
    if (!file) return;

    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      setError(locale === "it"
        ? `Formato non supportato: ${ext}. Usa Excel, CSV, Word, PDF o testo.`
        : `Unsupported format: ${ext}. Use Excel, CSV, Word, PDF, or text.`);
      return;
    }
    if (file.size > MAX_SIZE) {
      setError(locale === "it"
        ? "File troppo grande (max 10 MB)"
        : "File too large (max 10 MB)");
      return;
    }

    setError(null);
    setPreview(null);
    setSaved(false);
    setEditedMappings({});
    setEditingMapping(null);
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      setUploading(false);
      setParsing(true);

      const res = await fetch("/api/import/parse", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Upload failed (${res.status})`);
      }

      const result: ParseResult = await res.json();
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      setParsing(false);
    }
  }, [locale]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  const handleConfirm = useCallback(async () => {
    if (!preview) return;
    setSaving(true);
    setError(null);

    const sectionsWithEdits = preview.sections.map((section, idx) => {
      const edits = editedMappings[idx];
      if (!edits) return section;
      return { ...section, mappings: { ...section.mappings, ...Object.fromEntries(
        Object.entries(section.mappings).map(([orig, def]) => [orig, edits[orig] ?? def])
      )}};
    });

    try {
      const res = await fetch("/api/import/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sections: sectionsWithEdits, fileName: preview.fileName }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Save failed (${res.status})`);
      }

      setSaved(true);
      const histRes = await fetch("/api/import/history");
      if (histRes.ok) setHistory(await histRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [preview]);

  const handleUndo = useCallback(async (importId: string) => {
    try {
      const res = await fetch(`/api/import/undo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ importId }),
      });
      if (res.ok) {
        setHistory(h => h.filter(r => r.id !== importId));
      }
    } catch {}
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/setup">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="w-4 h-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-space-grotesk)]">
            {labels.title}
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">{labels.subtitle}</p>
        </div>
      </div>

      {/* Upload zone */}
      {!preview && !saved && (
        <Card>
          <CardContent className="p-0">
            <div
              className={`relative flex flex-col items-center justify-center gap-4 p-12 border-2 border-dashed rounded-lg transition-colors cursor-pointer ${
                dragActive
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-light)]"
                  : "border-[var(--color-border)] hover:border-[var(--color-accent)]/50"
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              {uploading || parsing ? (
                <>
                  <Loader2 className="w-8 h-8 text-[var(--color-accent)] animate-spin" />
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {parsing ? labels.parsing : labels.uploading}
                  </p>
                </>
              ) : (
                <>
                  <Upload className="w-8 h-8 text-[var(--color-text-muted)]" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-[var(--color-text)]">
                      {labels.dropHere}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      {labels.formats} · {labels.maxSize}
                    </p>
                  </div>
                  <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); fileRef.current?.click(); }}>
                    {labels.browse}
                  </Button>
                </>
              )}
              <input
                ref={fileRef}
                type="file"
                accept={ACCEPTED_TYPES.join(",")}
                className="hidden"
                onChange={(e) => e.target.files && handleFiles(e.target.files)}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {error && (
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto">
              <X className="w-4 h-4 text-[var(--color-text-muted)]" />
            </button>
          </CardContent>
        </Card>
      )}

      {/* Preview */}
      {preview && !saved && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-[var(--color-accent)]" />
              <span className="text-sm font-medium">{preview.fileName}</span>
              <Badge variant="outline" className="text-[10px]">
                ~${preview.cost_usd.toFixed(3)}
              </Badge>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setPreview(null); setSaved(false); }}
            >
              <X className="w-4 h-4 mr-1" />
              {labels.cancel}
            </Button>
          </div>

          {preview.sections.length === 0 && (
            <Card>
              <CardContent className="p-6 text-center">
                <FileText className="w-8 h-8 text-[var(--color-text-muted)] mx-auto mb-2" />
                <p className="text-sm text-[var(--color-text-muted)]">{labels.noData}</p>
              </CardContent>
            </Card>
          )}

          {preview.sections.map((section, i) => (
            <Card key={i}>
              <CardContent className="p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {categoryIcons[section.category]}
                    <h3 className="text-sm font-semibold">
                      {categoryLabel(section.category)}
                    </h3>
                  </div>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {labels.found} {section.rows.length} {labels.rows}
                  </span>
                </div>

                {/* Column mappings (editable) */}
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(section.mappings).map(([orig, defaultMapped]) => {
                    const mapped = getMappedName(i, orig, defaultMapped);
                    const isEditing = editingMapping?.section === i && editingMapping?.orig === orig;
                    return isEditing ? (
                      <span key={orig} className="inline-flex items-center gap-1 border border-[var(--color-accent)] rounded-full px-2 py-0.5 text-[10px] bg-white">
                        <span className="text-[var(--color-text-muted)]">{orig} →</span>
                        <Input
                          autoFocus
                          defaultValue={mapped}
                          className="h-5 w-24 text-[10px] px-1 py-0 border-0 bg-transparent focus-visible:ring-0"
                          onBlur={(e) => setMappedName(i, orig, e.target.value || defaultMapped)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") setMappedName(i, orig, (e.target as HTMLInputElement).value || defaultMapped);
                            if (e.key === "Escape") setEditingMapping(null);
                          }}
                        />
                      </span>
                    ) : (
                      <button
                        key={orig}
                        className="inline-flex items-center gap-1 border border-[var(--color-border)] rounded-full px-2 py-0.5 text-[10px] hover:border-[var(--color-accent)]/50 transition-colors group"
                        onClick={() => setEditingMapping({ section: i, orig })}
                      >
                        <span className="text-[var(--color-text-muted)]">{orig}</span>
                        <span>→</span>
                        <span className="font-medium">{mapped}</span>
                        <Pencil className="w-2.5 h-2.5 text-[var(--color-text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    );
                  })}
                </div>

                {/* Sample rows */}
                {section.rows.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-[var(--color-border)]">
                          {section.columns.map(col => (
                            <th key={col} className="text-left py-1.5 px-2 text-[var(--color-text-muted)] font-medium">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.rows.slice(0, 5).map((row, ri) => (
                          <tr key={ri} className="border-b border-[var(--color-border)]/50">
                            {section.columns.map(col => (
                              <td key={col} className="py-1.5 px-2 text-[var(--color-text)]">
                                {String(row[col] ?? "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {section.rows.length > 5 && (
                      <p className="text-[10px] text-[var(--color-text-muted)] mt-1 px-2">
                        + {section.rows.length - 5} more…
                      </p>
                    )}
                  </div>
                )}

                {/* Problems */}
                {section.problems.length > 0 && (
                  <div className="space-y-1 pt-2 border-t border-[var(--color-border)]">
                    <p className="text-xs font-medium text-amber-700">{labels.problems}</p>
                    {section.problems.map((p, pi) => (
                      <p key={pi} className="text-xs text-amber-600 flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3 shrink-0" />
                        {p.count !== undefined ? `${p.count} ${p.message}` : p.message}
                      </p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}

          {/* Global problems */}
          {preview.problems.length > 0 && (
            <Card>
              <CardContent className="p-4 space-y-1">
                <p className="text-xs font-medium text-amber-700">{labels.problems}</p>
                {preview.problems.map((p, pi) => (
                  <p key={pi} className="text-xs text-amber-600 flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    {p.count !== undefined ? `${p.count} ${p.message}` : p.message}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}

          {preview.sections.length > 0 && (
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setPreview(null)}>
                {labels.cancel}
              </Button>
              <Button onClick={handleConfirm} disabled={saving}>
                {saving ? (
                  <><Loader2 className="w-4 h-4 animate-spin mr-1" /> {labels.confirm}</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4 mr-1" /> {labels.confirm}</>
                )}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Success */}
      {saved && (
        <Card>
          <CardContent className="p-6 text-center space-y-3">
            <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
            <p className="text-sm font-medium">
              {locale === "it" ? "Importazione completata!" : "Import complete!"}
            </p>
            <Button variant="secondary" onClick={() => { setPreview(null); setSaved(false); }}>
              {locale === "it" ? "Importa un altro file" : "Import another file"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Import history */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <button
            className="flex items-center gap-2 text-sm font-semibold w-full text-left"
            onClick={async () => {
              setShowHistory(!showHistory);
              if (!showHistory) {
                const res = await fetch("/api/import/history");
                if (res.ok) setHistory(await res.json());
              }
            }}
          >
            <History className="w-4 h-4" />
            {labels.history}
          </button>

          {showHistory && (
            history.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)]">
                {locale === "it" ? "Nessuna importazione precedente" : "No previous imports"}
              </p>
            ) : (
              <div className="space-y-2">
                {history.map(rec => (
                  <div key={rec.id} className="flex items-center justify-between py-2 border-b border-[var(--color-border)]/50">
                    <div>
                      <p className="text-xs font-medium">{rec.fileName}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">
                        {new Date(rec.importedAt).toLocaleDateString(locale === "it" ? "it-IT" : "en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                        {" · "}
                        {rec.categories.map(c => categoryLabel(c)).join(", ")}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleUndo(rec.id)}
                      className="text-red-500 hover:text-red-700"
                    >
                      {labels.undo}
                    </Button>
                  </div>
                ))}
              </div>
            )
          )}
        </CardContent>
      </Card>

      {/* DPA / Privacy notice */}
      <Card>
        <CardContent className="p-5 flex items-start gap-3">
          <Shield className="w-5 h-5 text-[var(--color-accent)] shrink-0 mt-0.5" />
          <div className="text-xs text-[var(--color-text-muted)] space-y-1">
            <p className="font-medium text-[var(--color-text)]">
              {locale === "it" ? "Privacy e trattamento dati" : "Privacy & data processing"}
            </p>
            <p>{t(locale).setup.dpaNotice}</p>
            <p>{locale === "it"
              ? "I dati degli ospiti sono visibili solo a questo hotel. I dati importati possono essere eliminati in qualsiasi momento."
              : "Guest data is visible only to this hotel. Imported data can be deleted at any time."
            }</p>
          </div>
        </CardContent>
      </Card>

      {/* Delete all guest data */}
      <Card>
        <CardContent className="p-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Trash2 className="w-4 h-4 text-red-500" />
            <span className="text-sm font-medium text-red-700">{labels.deleteGuests}</span>
          </div>
          <Button
            variant="destructive"
            size="sm"
            onClick={async () => {
              if (!confirm(labels.deleteGuestsConfirm)) return;
              await fetch("/api/import/delete-guests", { method: "POST" });
            }}
          >
            {labels.deleteGuests}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
