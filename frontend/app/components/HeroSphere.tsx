"use client";

import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState, Suspense } from 'react'
import * as THREE from 'three'

interface HeroSphereProps {
    onHeroRevealed?: (label?: string) => void;
    onNotePosition?: (x: number, y: number) => void;
}

interface ImageItem {
    id: string;
    url: string;
    status: string;
    position: [number, number, number];
    isCluster: boolean;
}

function statusHex(status: string) {
    const map: Record<string, string> = {
        accepted: '#8f959a',
        needs_review: '#e9b872',
        rejected: '#d16b5a',
    }
    return map[status] || '#8f959a'
}

function HeroThumb({ item, revealed, hasCluster }: { item: ImageItem, revealed: boolean, hasCluster: boolean }) {
    const color = statusHex(item.status);
    const size = item.isCluster ? 1.1 : (0.5 + Math.random() * 0.4);
    const [imgFailed, setImgFailed] = useState(false);

    const showHighlight = hasCluster && item.isCluster && revealed;

    return (
        <group position={item.position}>
            <Html center distanceFactor={10} zIndexRange={[20, 0]} occlude={false}>
                <div
                    className="relative -translate-x-1/2 -translate-y-1/2 pointer-events-none transition-all duration-1000"
                    style={{
                        width: `${size * 60}px`,
                        height: `${size * 60}px`,
                        opacity: (hasCluster && item.isCluster && revealed) ? 1 : (hasCluster && revealed ? 0.6 : 0.95)
                    }}
                >
                    <span
                        className="absolute inset-0 rounded-xl transition-all duration-700 pointer-events-none"
                        style={{
                            boxShadow: showHighlight ? `0 0 0 2px ${color}, 0 0 20px ${color}` : `0 0 0 1px rgba(255,255,255,0.15)`,
                            transform: showHighlight ? 'scale(1.15)' : 'scale(1)',
                            backgroundColor: imgFailed ? (showHighlight ? color : 'rgba(255,255,255,0.1)') : 'transparent',
                        }}
                    >
                        {imgFailed && (
                            <span className="absolute inset-0 flex items-center justify-center text-[7px] font-mono font-bold text-center p-1 leading-tight text-white/30 truncate">
                                MEDIA
                            </span>
                        )}
                    </span>
                    {!imgFailed && (
                        <img
                            src={item.url}
                            alt=""
                            draggable={false}
                            onError={() => setImgFailed(true)}
                            className="absolute inset-0 h-full w-full rounded-xl object-cover"
                            style={{ transform: showHighlight ? 'scale(1.15)' : 'scale(1)' }}
                        />
                    )}
                </div>
            </Html>
        </group>
    )
}

function HeroScene({ images, hasCluster, revealLabel, onHeroRevealed, onNotePosition }: { images: ImageItem[], hasCluster: boolean, revealLabel: string } & HeroSphereProps) {
    const groupRef = useRef<THREE.Group>(null);
    const { camera, size } = useThree();
    const [revealed, setRevealed] = useState(false);

    const clusterCenter = useMemo(() => {
        if (!hasCluster) return null;
        const cgs = images.filter(i => i.isCluster);
        if (cgs.length === 0) return null;
        const center = new THREE.Vector3();
        cgs.forEach(c => center.add(new THREE.Vector3(...c.position)));
        return center.divideScalar(cgs.length);
    }, [images, hasCluster]);

    useEffect(() => {
        let t = setTimeout(() => {
            if (hasCluster) {
                setRevealed(true);
                if (onHeroRevealed) onHeroRevealed(revealLabel);
            }
        }, 1800);
        return () => clearTimeout(t);
    }, [onHeroRevealed, hasCluster, revealLabel]);

    useFrame((state) => {
        const t = state.clock.elapsedTime;
        const mouseX = state.pointer.x * 0.5;
        const mouseY = state.pointer.y * 0.5;

        if (groupRef.current) {
            groupRef.current.rotation.y = t * 0.12 + mouseX * 0.3;
            groupRef.current.rotation.x = mouseY * 0.15;
            groupRef.current.updateMatrixWorld();

            if (onNotePosition && revealed && clusterCenter) {
                const vector = clusterCenter.clone();
                vector.applyMatrix4(groupRef.current.matrixWorld);
                vector.project(camera);
                const px = (vector.x * 0.5 + 0.5) * size.width;
                const py = (-vector.y * 0.5 + 0.5) * size.height;
                onNotePosition(px, py);
            }
        }
    });

    return (
        <group>
            <fogExp2 attach="fog" args={[0x0e1013, 0.052]} />
            <ambientLight intensity={0.6} />

            <mesh>
                <sphereGeometry args={[7.4, 24, 16]} />
                <meshBasicMaterial color="#8f959a" wireframe transparent opacity={0.05} />
            </mesh>

            <group ref={groupRef}>
                {images.map(item => (
                    <HeroThumb key={item.id} item={item} revealed={revealed} hasCluster={hasCluster} />
                ))}
            </group>

            <OrbitControls enablePan={false} autoRotate autoRotateSpeed={0.5} minDistance={6} maxDistance={20} enableDamping dampingFactor={0.08} />
        </group>
    );
}

const AMBIENT_PATHS = Array.from({ length: 17 }, (_, i) => `/hero-demo/demo_${i + 1}.jpg`);

const CLUSTER_ITEMS = [
    { id: "demo_0", url: "/hero-demo/demo_0.jpg", status: "accepted" },
    { id: "demo_0_recompressed", url: "/hero-demo/demo_0_recompressed.jpg", status: "rejected" },
    { id: "demo_0_rotated", url: "/hero-demo/demo_0_rotated.jpg", status: "rejected" },
];

export default function HeroSphere({ onHeroRevealed, onNotePosition }: HeroSphereProps) {
    const { images, hasCluster, revealLabel } = useMemo(() => {
        // Based on real hamming values computed via imagehash
        // recompressed: 0 -> 100% confidence
        // rotated: 18 -> (1 - 18/64) * 100 = ~72% confidence
        const cLabel = `3 images matched — NEAR DUPLICATE, 72% confidence`;

        const ambientItems = AMBIENT_PATHS.map((path, idx) => ({ id: `ambient_${idx}`, url: path, status: "accepted" }));
        const combinedItems = [...CLUSTER_ITEMS, ...ambientItems].slice(0, 20);

        const count = combinedItems.length;
        const radius = 3.6;
        const golden = Math.PI * (3 - Math.sqrt(5));

        const basePositions: number[][] = [];
        for (let i = 0; i < count; i++) {
            const y = 1 - (i / Math.max(1, count - 1)) * 2;
            const r = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = golden * i;
            basePositions.push([
                Math.cos(theta) * r * radius,
                y * radius,
                Math.sin(theta) * r * radius
            ]);
        }

        if (count > 0) {
            const center = basePositions[0];
            const jitters = [
                [-0.2, 0.3, 0.1],
                [0.15, -0.2, 0.25],
                [-0.3, 0.1, -0.2],
            ];
            for (let i = 0; i < CLUSTER_ITEMS.length; i++) {
                const jidx = i % jitters.length;
                basePositions[i] = [
                    center[0] + jitters[jidx][0],
                    center[1] + jitters[jidx][1],
                    center[2] + jitters[jidx][2]
                ];
            }
        }

        const mappedImages: ImageItem[] = combinedItems.map((data: any, idx: number) => {
            const isCluster = idx < CLUSTER_ITEMS.length;
            return {
                id: data.id,
                url: data.url,
                status: isCluster ? "needs_review" : data.status,
                position: basePositions[idx] as [number, number, number],
                isCluster
            };
        });

        return { images: mappedImages, hasCluster: true, revealLabel: cLabel };
    }, []);

    return (
        <div className="absolute inset-0 z-0 pointer-events-auto">
            {images.length > 0 && (
                <Canvas camera={{ position: [0, 0, 10], fov: 45 }} gl={{ antialias: true, alpha: true }} dpr={[1, 2]}>
                    <Suspense fallback={null}>
                        <HeroScene
                            images={images}
                            hasCluster={hasCluster}
                            revealLabel={revealLabel}
                            onHeroRevealed={onHeroRevealed}
                            onNotePosition={onNotePosition}
                        />
                    </Suspense>
                </Canvas>
            )}
        </div>
    );
}
