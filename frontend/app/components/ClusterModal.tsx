"use client";

import { Canvas, useFrame } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import { Loader2, Move3d, X, Crown } from 'lucide-react'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

interface GraphNode {
    id: string;
    isCanonical: boolean;
    position: [number, number, number];
    score: number;
    scoreType?: string;
    status: string;
    imageUrl?: string;
    filename?: string;
}

interface ClusterGraph {
    nodes: GraphNode[];
    label: string;
}

function statusHex(status: string) {
    const map: Record<string, string> = {
        accepted: '#8f959a',
        needs_review: '#e9b872',
        rejected: '#d16b5a',
    }
    return map[status] || '#8f959a'
}

function CanonicalCore() {
    const ref = useRef<THREE.Mesh>(null)
    const halo = useRef<THREE.Mesh>(null)
    useFrame((state) => {
        const t = state.clock.elapsedTime
        const s = 1 + Math.sin(t * 1.6) * 0.06
        if (ref.current) ref.current.scale.setScalar(s)
        if (halo.current) {
            halo.current.scale.setScalar(1.4 + Math.sin(t * 1.6) * 0.12)
                ; (halo.current.material as THREE.MeshBasicMaterial).opacity = 0.18 + Math.sin(t * 1.6) * 0.05
        }
    })
    return (
        <group>
            <pointLight color="#e9b872" intensity={12} distance={16} />
            <mesh ref={ref}>
                <icosahedronGeometry args={[0.55, 2]} />
                <meshBasicMaterial color="#e9b872" />
            </mesh>
            <mesh ref={halo}>
                <sphereGeometry args={[0.55, 24, 24]} />
                <meshBasicMaterial color="#e9b872" transparent opacity={0.2} side={THREE.BackSide} />
            </mesh>
        </group>
    )
}

function SimilarityPacket({ from, score, phase, color }: { from: THREE.Vector3; score: number; phase: number; color: string }) {
    const ref = useRef<THREE.Mesh>(null)
    const to = useMemo(() => new THREE.Vector3(0, 0, 0), [])
    const speed = 0.18 + score * 0.55
    useFrame((state) => {
        if (!ref.current) return
        const t = (state.clock.elapsedTime * speed + phase) % 1
        ref.current.position.lerpVectors(from, to, t)
        const scale = 0.06 + Math.sin(t * Math.PI) * 0.05
        ref.current.scale.setScalar(scale)
    })
    return (
        <mesh ref={ref}>
            <sphereGeometry args={[1, 12, 12]} />
            <meshBasicMaterial color={color} />
        </mesh>
    )
}

function NodeThumb({ node }: { node: GraphNode }) {
    const [hovered, setHovered] = useState(false)
    const [imgFailed, setImgFailed] = useState(false)
    const color = statusHex(node.status)
    const size = 0.5 + node.score * 0.6

    return (
        <group position={node.position}>
            <Html center distanceFactor={9} zIndexRange={[20, 0]} occlude={false}>
                <button
                    type="button"
                    onPointerOver={() => setHovered(true)}
                    onPointerOut={() => setHovered(false)}
                    className="group relative -translate-x-1/2 -translate-y-1/2 outline-none cursor-pointer"
                    style={{ width: `${size * 90}px`, height: `${size * 90}px` }}
                >
                    <span
                        className="absolute inset-0 rounded-xl transition-all duration-200"
                        style={{
                            boxShadow: `0 0 0 2px ${color}, 0 0 ${hovered ? 26 : 14}px ${color}`,
                            transform: hovered ? 'scale(1.15)' : 'scale(1)',
                            backgroundColor: imgFailed ? color : 'transparent',
                        }}
                    >
                        {imgFailed && (
                            <span className="absolute inset-0 flex items-center justify-center text-[10px] font-mono text-black/40 font-bold uppercase tracking-wider text-center p-2 leading-tight">
                                NO MEDIA<br />PATH
                            </span>
                        )}
                    </span>
                    {!imgFailed && (
                        <img
                            src={node.imageUrl || '/placeholder.svg'}
                            alt=""
                            draggable={false}
                            onError={() => setImgFailed(true)}
                            className="absolute inset-0 h-full w-full rounded-xl object-cover"
                            style={{ transform: hovered ? 'scale(1.15)' : 'scale(1)' }}
                        />
                    )}
                    <span
                        className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full flex flex-col items-center rounded-md px-2 py-1 font-mono text-[11px] font-bold text-black shadow-md transition-all duration-200"
                        style={{ background: color, transform: hovered ? 'scale(1.15)' : 'scale(1)' }}
                    >
                        {Math.round(node.score * 100)}%
                        {node.scoreType === 'hash-based' && (
                            <span className="text-[7.5px] font-fraunces leading-none uppercase opacity-80 border-t border-black/20 pt-[3px] mt-[3px] w-full text-center">Hash Match</span>
                        )}
                    </span>

                    {hovered && (
                        <span className="absolute top-full mt-3 left-1/2 -translate-x-1/2 whitespace-nowrap bg-black/80 text-white font-mono text-[10px] px-2 py-1.5 rounded backdrop-blur border border-white/10 z-50">
                            {node.filename}
                        </span>
                    )}
                </button>
            </Html>
        </group>
    )
}

export function ClusterScene({ graph }: { graph: ClusterGraph }) {
    const dupNodes = graph.nodes.filter((n) => !n.isCanonical)

    return (
        <>
            <ambientLight intensity={0.6} />
            <CanonicalCore />

            <mesh>
                <sphereGeometry args={[7.4, 24, 16]} />
                <meshBasicMaterial color="#8f959a" wireframe transparent opacity={0.06} />
            </mesh>

            {dupNodes.map((node) => {
                const color = statusHex(node.status)
                const from = new THREE.Vector3(...node.position)
                let nodeHash = 0
                for (let i = 0; i < node.id.length; i++) nodeHash += node.id.charCodeAt(i)
                return (
                    <group key={node.id}>
                        <Line points={[node.position, [0, 0, 0]]} color={color} transparent opacity={0.12 + node.score * 0.25} lineWidth={0.6 + node.score} />
                        <SimilarityPacket from={from} score={node.score} phase={(nodeHash % 10) / 10} color={color} />
                    </group>
                )
            })}

            {graph.nodes.map((node) =>
                node.isCanonical ? (
                    <Html key={node.id} position={[0, -1.15, 0]} center distanceFactor={10}>
                        <div className="flex -translate-x-1/2 items-center gap-1.5 whitespace-nowrap rounded-full bg-black/80 px-2.5 py-1 text-[11px] font-mono text-white backdrop-blur border border-[#e9b872]/30">
                            <Crown className="size-3 text-[#e9b872]" />
                            ROOT RECORD
                        </div>
                    </Html>
                ) : (
                    <NodeThumb key={node.id} node={node} />
                ),
            )}

            <OrbitControls enablePan={false} autoRotate autoRotateSpeed={0.5} minDistance={6} maxDistance={25} enableDamping dampingFactor={0.08} />
        </>
    )
}

export default function ClusterModal({ imageId, onClose }: { imageId: string; onClose: () => void }) {
    const [graph, setGraph] = useState<ClusterGraph | null>(null)

    useEffect(() => {
        let active = true;
        const fetchGraph = async () => {
            try {
                const url = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const res = await fetch(`${url}/images/${imageId}/cluster`)
                if (!res.ok) throw new Error("Fetch failed");
                const json = await res.json()

                if (!active) return;

                const rootNode: GraphNode = {
                    id: json.root.id,
                    isCanonical: true,
                    position: [0, 0, 0],
                    score: 1,
                    status: json.root.status,
                    imageUrl: `${url}/images/${json.root.id}/file`,
                    filename: json.root.filename
                }

                const count = json.duplicates?.length || 0
                const golden = Math.PI * (3 - Math.sqrt(5))

                const dupNodes = json.duplicates?.map((dup: any, i: number) => {
                    let score = 0.5;
                    let scoreType = "fallback";
                    if (dup.similarity !== null && dup.similarity !== undefined) {
                        score = dup.similarity;
                        scoreType = "semantic";
                    } else if (dup.hamming_distance !== null && dup.hamming_distance !== undefined) {
                        score = Math.max(0, Math.min(1, 1 - (dup.hamming_distance / 64)));
                        scoreType = "hash-based";
                    }

                    const radius = 5 + (1 - score) * 8.5; // High score = closer to core
                    const y = 1 - (i / Math.max(1, count - 1)) * 2;
                    const r = Math.sqrt(Math.max(0, 1 - y * y));
                    const theta = golden * i;

                    return {
                        id: dup.id,
                        isCanonical: false,
                        position: [
                            Math.cos(theta) * r * radius,
                            y * radius,
                            Math.sin(theta) * r * radius
                        ] as [number, number, number],
                        score,
                        scoreType,
                        status: dup.status,
                        imageUrl: `${url}/images/${dup.id}/file`,
                        filename: dup.filename
                    }
                }) || [];

                setGraph({ nodes: [rootNode, ...dupNodes], label: json.root.filename })
            } catch (err) {
                console.error("Cluster modal fetch error", err)
            }
        }
        setGraph(null);
        fetchGraph()
        return () => { active = false }
    }, [imageId])

    useEffect(() => {
        function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [onClose])

    return (
        <div className="fixed inset-0 z-50 flex flex-col bg-black/85 backdrop-blur-xl transition-all">
            <header className="relative flex items-center justify-between gap-3 px-6 py-4 z-10 pointer-events-auto border-b border-white/5 bg-black/40">
                <div className="flex flex-col gap-1">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-[#8f959a]">Cluster Explorer</p>
                    <h2 className="text-xl font-fraunces font-semibold text-white/90">{graph?.label ?? 'Loading cluster...'}</h2>
                </div>
                <div className="flex items-center gap-4">
                    <span className="hidden items-center gap-2 rounded-full border border-white/10 bg-black/60 px-4 py-1.5 font-mono text-xs text-[#8f959a] sm:flex shadow-sm">
                        <Move3d className="size-3.5" /> Drag to orbit / Scroll to zoom
                    </span>
                    <button
                        onClick={onClose}
                        className="p-2.5 rounded-full hover:bg-white/10 text-white/80 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </header>

            <div className="relative min-h-0 flex-1">
                {!graph ? (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <span className="flex items-center gap-3 text-sm font-mono text-[#8f959a] uppercase tracking-widest">
                            <Loader2 className="size-5 animate-spin text-[#e9b872]" /> Reconstructing 3D layout Wait...
                        </span>
                    </div>
                ) : graph.nodes.length === 1 ? (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <span className="flex flex-col items-center gap-2 font-mono text-[#8f959a] text-sm uppercase tracking-widest">
                            <div className="w-24 h-24 rounded-2xl overflow-hidden shadow-2xl mb-4 border-2 border-white/10 opacity-80">
                                <img src={graph.nodes[0].imageUrl} alt="Root" className="w-full h-full object-cover" />
                            </div>
                            No duplicates found for this image
                        </span>
                    </div>
                ) : (
                    <Canvas camera={{ position: [0, 2, 11], fov: 50 }} gl={{ alpha: true, antialias: true }} dpr={[1, 2]}>
                        <Suspense fallback={null}>
                            <ClusterScene graph={graph} />
                        </Suspense>
                    </Canvas>
                )}
            </div>
        </div>
    )
}
