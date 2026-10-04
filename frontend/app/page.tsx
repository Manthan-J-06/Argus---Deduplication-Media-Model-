"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import "./hero.css";
import HeroSphere from "./components/HeroSphere";

export default function HeroPage() {
  const noteRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const handleHeroRevealed = (label?: string) => {
    if (noteRef.current) {
      if (label) {
        const span = noteRef.current.querySelector('span');
        if (span) span.textContent = label;
      }
      noteRef.current.classList.add("visible");
    }
  };

  const handleNotePosition = (x: number, y: number) => {
    if (!noteRef.current) return;
    noteRef.current.style.left = x + 18 + "px";
    noteRef.current.style.top = y - 10 + "px";
  };

  return (
    <main className="relative w-full">
      {/* Background 3D elements - fixed to viewport */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <HeroSphere
          onHeroRevealed={handleHeroRevealed}
          onNotePosition={handleNotePosition}
        />
        <div className="glow"></div>
        <div className="vignette"></div>
      </div>

      {/* Fold 1 - Hero Content */}
      <section className="relative w-full h-[100vh] pointer-events-none">
        <nav className="hero-nav pointer-events-auto">
          <div className="logo">Argus</div>
          <div className="links">
            <a href="#how-it-works">How it works</a>
            <Link href="/dashboard">Start triaging</Link>
          </div>
        </nav>

        <div className="hero pointer-events-auto">
          <h1>Your library has the same photo more than once.<br /><span className="dim">It just doesn't look like it.</span></h1>
          <p>A screenshot re-saved at 60% quality. A photo cropped for Instagram. Two shots of the same sunset, ten seconds apart. Argus finds all of it — exact, near, and semantic — and shows you exactly why, before anything gets deleted.</p>
          <div className="tiers">
            <div className="tier"><div className="dot" style={{ background: '#8f959a' }}></div><span>Exact match</span></div>
            <div className="tier"><div className="dot" style={{ background: '#7d8a94' }}></div><span>Near-duplicate</span></div>
            <div className="tier"><div className="dot" style={{ background: '#d16b5a' }}></div><span>Same subject</span></div>
          </div>
          <div className="hero-actions">
            <button className="btn-primary" onClick={() => router.push('/dashboard')}>Upload a batch</button>
          </div>
        </div>

        <div className="cluster-note pointer-events-none" ref={noteRef}>
          <div className="dot"></div>
          <span>3 images, same subject — flagged for review</span>
        </div>
      </section>

      {/* Fold 2 - How it works */}
      <section id="how-it-works" className="relative z-10 w-full min-h-[50vh] bg-[#0e1013]/95 border-t border-white/5 py-32 px-12 sm:px-24 flex flex-col items-center justify-center pointer-events-auto shadow-[0_-20px_50px_rgba(0,0,0,0.5)]">
        <div className="max-w-4xl w-full grid grid-cols-1 md:grid-cols-3 gap-16">
          <div className="flex flex-col gap-4">
            <h3 className="text-xl font-fraunces font-semibold text-[#e7e5e0]">1. Upload</h3>
            <p className="font-mono text-[13.5px] leading-relaxed text-[#868c92]">Drop a batch of photos.</p>
          </div>
          <div className="flex flex-col gap-4">
            <h3 className="text-xl font-fraunces font-semibold text-[#e7e5e0]">2. Detect</h3>
            <p className="font-mono text-[13.5px] leading-relaxed text-[#868c92]">Three tiers of matching, in order: hash, near-hash, semantic.</p>
          </div>
          <div className="flex flex-col gap-4">
            <h3 className="text-xl font-fraunces font-semibold text-[#e7e5e0]">3. Review</h3>
            <p className="font-mono text-[13.5px] leading-relaxed text-[#868c92]">Nothing gets deleted without you confirming it.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
