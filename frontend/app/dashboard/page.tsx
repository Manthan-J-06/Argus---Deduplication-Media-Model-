"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import ClusterModal from "../components/ClusterModal";

export default function TriagePage() {
  const [images, setImages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState("All");

  const [isDragging, setIsDragging] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{ active: boolean; text?: string; total: number; processed: number } | null>(null);
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importUrl, setImportUrl] = useState("");

  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = () => setIsDragging(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  const processFiles = async (fileList: FileList) => {
    setUploadError(null);
    setUploadStatus(null);
    setBatchProgress(null);

    const files = Array.from(fileList);
    if (files.length === 0) return;

    if (files.length === 1) {
      const file = files[0];
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/images/check`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) throw new Error("Upload failed");
        const data = await res.json();

        const returnedImage = data.image || data;
        const statusText = returnedImage.status || "uploaded";
        const reason = returnedImage.reason_code ? `(${returnedImage.reason_code})` : '';
        setUploadStatus(`${file.name} — ${statusText} ${reason}`);

        if (statusFilter === "All" || statusFilter === returnedImage.status ||
          (statusFilter === "Needs Review" && returnedImage.status === "needs_review") ||
          (statusFilter === "Rejected" && returnedImage.status === "rejected") ||
          (statusFilter === "Accepted" && returnedImage.status === "accepted")) {
          setImages(prev => [returnedImage, ...prev]);
        }
      } catch (err: any) {
        setUploadError(`Failed to upload ${file.name}: ${err.message}`);
      }
    } else {
      const formData = new FormData();
      files.forEach(f => formData.append("files", f));

      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/images/batch-check`, {
          method: 'POST',
          body: formData,
        });
        if (!res.ok) throw new Error("Batch upload failed");

        const data = await res.json();
        if (!data.job_id) throw new Error("No job ID returned");

        setBatchProgress({ active: true, total: files.length, processed: 0, text: `Processing ${files.length} images...` });

        const pollJob = async () => {
          try {
            const jobRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/jobs/${data.job_id}`);
            if (!jobRes.ok) throw new Error("Poll failed");
            const jobData = await jobRes.json();

            if (jobData.status === "complete") {
              setBatchProgress(null);
              setUploadStatus(`Batch processing complete for ${files.length} images`);
              fetchImages(1, statusFilter);
            } else if (jobData.status === "failed") {
              setBatchProgress(null);
              setUploadError("Batch job failed on server.");
            } else {
              setBatchProgress(prev => prev ? { ...prev, text: `Processing ${files.length} images... ${jobData.processed || 0}/${files.length} done` } : null);
              setTimeout(pollJob, 1500);
            }
          } catch {
            setTimeout(pollJob, 1500);
          }
        };
        setTimeout(pollJob, 1500);

      } catch (err: any) {
        setUploadError(err.message);
      }
    }
  };

  const handleImportUrl = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!importUrl.trim()) return;

    setUploadError(null);
    setUploadStatus(null);
    setBatchProgress(null);

    const targetUrl = importUrl.trim();

    try {
      setBatchProgress({ active: true, total: 0, processed: 0, text: `Starting URL import...` });

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/images/import-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: targetUrl }),
      });

      if (!res.ok) {
        let errorMsg = `HTTP error ${res.status}`;
        try {
          const errorData = await res.json();
          errorMsg = errorData.detail || errorData.error || errorMsg;
        } catch {
          // Ignore json parse error
        }
        throw new Error(errorMsg);
      }

      const data = await res.json();
      if (!data.job_id) throw new Error("No job ID returned");

      setBatchProgress({ active: true, total: 0, processed: 0, text: `Processing import...` });

      const pollImportJob = async () => {
        try {
          const jobRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/jobs/${data.job_id}`);
          if (!jobRes.ok) throw new Error("Poll failed");
          const jobData = await jobRes.json();

          if (jobData.status === "complete") {
            setBatchProgress(null);
            setUploadStatus(`Import processing complete`);
            setImportUrl("");
            fetchImages(1, statusFilter);
          } else if (jobData.status === "failed") {
            setBatchProgress(null);
            setUploadError(`Import failed: ${jobData.error || "Unknown error"}`);
          } else {
            const total = jobData.total || 0;
            const processed = jobData.processed || 0;
            const text = total > 1
              ? `Processing... ${processed}/${total} done`
              : `Processing import...`;
            setBatchProgress(prev => prev ? { ...prev, text } : null);
            setTimeout(pollImportJob, 1500);
          }
        } catch {
          setTimeout(pollImportJob, 1500);
        }
      };

      setTimeout(pollImportJob, 1500);
    } catch (err: any) {
      setBatchProgress(null);
      setUploadError(err.message || "Import failed");
    }
  };

  const fetchImages = useCallback(async (pageNum: number, status: string) => {
    setLoading(true);
    try {
      const url = new URL(process.env.NEXT_PUBLIC_API_URL + "/images");
      url.searchParams.append("page", pageNum.toString());
      url.searchParams.append("page_size", "50");
      if (status !== "All") {
        let backendFilter = status;
        if (status === "Needs Review") backendFilter = "needs_review";
        if (status === "Rejected") backendFilter = "rejected";
        if (status === "Accepted") backendFilter = "accepted";
        url.searchParams.append("status", backendFilter);
      }

      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        setImages(data.items || []);
        setPage(data.page || 1);
        setTotalPages(data.total_pages || 1);
      }
    } catch (err) {
      console.error("Failed to fetch images", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchImages(page, statusFilter);
  }, [page, statusFilter, fetchImages]);

  const handleReview = async (id: string, decision: string) => {
    const imgIndex = images.findIndex(img => img.id === id);
    if (imgIndex === -1) return;

    const oldImage = images[imgIndex];

    // Optimistic UI updates
    setImages(prev => {
      const newList = [...prev];
      newList[imgIndex] = {
        ...newList[imgIndex],
        status: decision,
        reason_code: "MANUAL_REVIEW",
        reviewed_by_human: true,
        error: undefined
      };
      return newList;
    });

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/images/${id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision })
      });
      if (!res.ok) throw new Error('API failure');

      // Auto-remove if filter mismatch
      if (statusFilter !== "All") {
        const matchesFilter =
          (statusFilter === "Needs Review" && decision === "needs_review") ||
          (statusFilter === "Rejected" && decision === "rejected") ||
          (statusFilter === "Accepted" && decision === "accepted");

        if (!matchesFilter) {
          setTimeout(() => {
            setImages(prev => prev.filter(img => img.id !== id));
          }, 400);
        }
      }
    } catch (err) {
      console.error(err);
      // Revert optimism and set error
      setImages(prev => {
        const newList = [...prev];
        const idx = newList.findIndex(img => img.id === id);
        if (idx !== -1) {
          newList[idx] = { ...oldImage, error: "Update failed" };
        }
        return newList;
      });
    }
  };

  const StatusDot = ({ status }: { status: string }) => {
    let color = "bg-muted";
    if (status === "needs_review") color = "bg-accent-review";
    if (status === "rejected") color = "bg-accent";

    return <span className={`inline-block w-2 h-2 rounded-full ${color} shrink-0`} title={status} />;
  };

  return (
    <main className="min-h-screen p-6 max-w-[1700px] mx-auto font-['var(--font-plex-mono)']">
      <header className="flex flex-col mb-8 pb-4 border-b border-border">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-['var(--font-fraunces)'] tracking-wide text-primary">ARGUS.</h1>
        </div>

        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`w-full border border-dashed rounded p-6 flex flex-col items-center justify-center cursor-pointer transition-colors mb-6 relative overflow-hidden
              ${isDragging ? "border-primary bg-bg" : "border-border hover:border-border-hover bg-surface"}`}
        >
          <input type="file" multiple accept="image/*" className="hidden" ref={fileInputRef} onChange={(e) => { e.target.files && processFiles(e.target.files); e.target.value = ''; }} />
          <span className="text-sm text-muted uppercase tracking-widest font-medium z-10">Drop images here or click to browse</span>

          {batchProgress?.active && (
            <div className="mt-4 text-xs text-accent-review uppercase font-medium flex items-center justify-center gap-2 z-10 w-full text-center tabular-nums">
              <span className="animate-spin inline-block w-3 h-3 border-2 border-accent-review border-t-transparent rounded-full" />
              {batchProgress.text}
            </div>
          )}
          {uploadStatus && (
            <div className="mt-2 text-xs text-[#a3b18a] uppercase font-medium z-10">{uploadStatus}</div>
          )}
          {uploadError && (
            <div className="mt-2 text-xs text-accent uppercase font-medium z-10">{uploadError}</div>
          )}
        </div>

        <form
          onSubmit={handleImportUrl}
          className="w-full border border-border bg-surface rounded p-4 flex items-center gap-3 mb-6 transition-colors hover:border-border-hover"
        >
          <input
            type="text"
            value={importUrl}
            onChange={(e) => setImportUrl(e.target.value)}
            placeholder="Paste an image URL or a .zip URL"
            className="flex-1 bg-bg border border-border rounded px-3 py-2 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
          />
          <button
            type="submit"
            disabled={!importUrl.trim()}
            className="px-4 py-2 bg-primary text-bg rounded text-xs font-semibold uppercase tracking-widest hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            Import
          </button>
        </form>

        <div className="flex gap-2 self-start">
          {["All", "Needs Review", "Rejected", "Accepted"].map((filter) => (
            <button
              key={filter}
              onClick={() => {
                setStatusFilter(filter);
                setPage(1);
              }}
              className={`px-4 py-1.5 text-xs uppercase tracking-widest font-medium transition-colors border ${statusFilter === filter
                ? "bg-bg border-border text-primary"
                : "bg-transparent border-transparent text-muted hover:text-primary"
                }`}
            >
              {filter}
            </button>
          ))}
        </div>
      </header>

      {loading ? (
        <div className="text-center text-muted text-sm my-32 uppercase tracking-widest animate-pulse">Loading Pipeline...</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 2xl:grid-cols-6 gap-4">
          {images.map((img: any) => (
            <div key={img.id} className="group relative flex flex-col bg-surface border border-border overflow-hidden transition hover:border-border-hover cursor-pointer" onClick={() => setSelectedClusterId(img.id)}>
              <div className="aspect-[4/3] bg-bg flex items-center justify-center relative overflow-hidden border-b border-border/50">
                <ImagePlaceholder
                  src={`${process.env.NEXT_PUBLIC_API_URL}/images/${img.id}/file`}
                  alt={img.filename}
                />

                {/* OVERLAY ACTION BUTTONS */}
                <div className="absolute inset-x-0 bottom-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity flex justify-center gap-2 bg-gradient-to-t from-black/80 to-transparent">
                  <button
                    onClick={(e) => { e.stopPropagation(); handleReview(img.id, 'accepted'); }}
                    className="px-3 py-1.5 text-xs font-semibold bg-primary/90 text-bg hover:bg-primary transition-colors rounded-sm shadow-sm"
                  >
                    Accept
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleReview(img.id, 'rejected'); }}
                    className="px-3 py-1.5 text-xs font-semibold bg-accent/90 text-primary hover:bg-accent transition-colors rounded-sm shadow-sm"
                  >
                    Reject
                  </button>
                </div>
              </div>
              <div className="p-3 flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2 w-full">
                  <span className="truncate text-[11px] text-secondary font-medium" title={img.filename}>
                    {img.filename}
                  </span>
                  <StatusDot status={img.status} />
                </div>

                <div className="text-[10px] uppercase text-muted font-medium tracking-wide flex items-center justify-between">
                  {img.reason_code || "N/A"}
                  {img.reviewed_by_human && <span className="text-accent/80 font-bold ml-1" title="Manual Override">[M]</span>}
                </div>
                {img.error && (
                  <div className="text-[10px] text-red-400 mt-1">{img.error}</div>
                )}
              </div>
            </div>
          ))}
          {images.length === 0 && (
            <div className="col-span-full text-center text-muted text-sm my-20 uppercase tracking-widest">
              No captures match filtering logic - Wait for Background Service.
            </div>
          )}
        </div>
      )}

      <footer className="mt-12 mb-8 pt-4 flex items-center justify-between border-t border-border text-xs uppercase tracking-widest">
        <button
          disabled={page <= 1}
          onClick={() => setPage(p => Math.max(1, p - 1))}
          className="px-5 py-2.5 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-bg transition-colors border border-border text-muted hover:text-primary"
        >
          Previous
        </button>
        <span className="text-muted">
          Page {page} / {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => setPage(p => Math.min(totalPages, p + 1))}
          className="px-5 py-2.5 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-bg transition-colors border border-border text-muted hover:text-primary"
        >
          Next
        </button>
      </footer>

      {selectedClusterId && (
        <ClusterModal imageId={selectedClusterId} onClose={() => setSelectedClusterId(null)} />
      )}
    </main>
  );
}

// Fallback component
function ImagePlaceholder({ src, alt }: { src: string, alt: string }) {
  const [error, setError] = useState(false);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full bg-surface inset-0 absolute">
        <span className="text-[10px] text-muted block px-2 text-center break-all uppercase tracking-widest">[ No Media Path ]</span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      onError={() => { console.log('Image load error for src:', src); setError(true); }}
      className="absolute inset-0 w-full h-full object-cover transition-opacity duration-300"
    />
  );
}
