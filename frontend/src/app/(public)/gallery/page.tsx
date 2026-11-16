'use client';

import React, { useState, useEffect } from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { Alert } from '@/components/ui/Alert';
import { fetchPublicGallery, fetchPublicGalleryAlbum, resolveMediaUrl } from '@/lib/api';
import { PublicGalleryAlbum, PublicGalleryAlbumDetail } from '@/lib/types';

function getCategoryLabel(catDisplay?: string | null, lang?: string): string {
  if (!catDisplay) return '';
  if (catDisplay.includes(' / ')) {
    const parts = catDisplay.split(' / ');
    return lang === 'en' ? parts[0].trim() : (parts[1]?.trim() || parts[0].trim());
  }
  return catDisplay;
}

function formatAlbumDate(dateStr?: string | null, lang?: string): string | null {
  if (!dateStr) return null;
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleDateString(lang === 'mr' ? 'mr-IN' : 'en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export default function GalleryPage() {
  const { t, language } = useLanguage();
  const [category, setCategory] = useState<string>('');
  const [albums, setAlbums] = useState<PublicGalleryAlbum[]>([]);
  const [loading, setLoading] = useState(true);

  // Lightbox & Album viewer state
  const [selectedAlbum, setSelectedAlbum] = useState<PublicGalleryAlbumDetail | null>(null);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [loadingAlbumId, setLoadingAlbumId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    fetchPublicGallery(language, category).then((data) => {
      if (isMounted) {
        if (data && Array.isArray(data.results)) {
          setAlbums(data.results as PublicGalleryAlbum[]);
        } else {
          setAlbums([]);
        }
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, category]);

  // Keyboard navigation for accessible lightbox
  useEffect(() => {
    if (lightboxIndex === null || !selectedAlbum) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setLightboxIndex(null);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setLightboxIndex((prev) =>
          prev !== null && prev > 0 ? prev - 1 : (selectedAlbum?.photos.length || 1) - 1
        );
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setLightboxIndex((prev) =>
          prev !== null && prev < (selectedAlbum?.photos.length || 1) - 1 ? prev + 1 : 0
        );
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [lightboxIndex, selectedAlbum]);

  async function handleOpenAlbum(album: PublicGalleryAlbum) {
    setLoadingAlbumId(album.id);
    try {
      const detail = await fetchPublicGalleryAlbum(album.slug || album.id, language);
      if (detail && detail.photos && detail.photos.length > 0) {
        setSelectedAlbum(detail);
        setLightboxIndex(0);
      } else if (detail) {
        setSelectedAlbum(detail);
      }
    } catch (err) {
      console.error('Failed to load album photos', err);
    } finally {
      setLoadingAlbumId(null);
    }
  }

  const currentPhoto =
    selectedAlbum && lightboxIndex !== null && selectedAlbum.photos[lightboxIndex]
      ? selectedAlbum.photos[lightboxIndex]
      : null;

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.gallery.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.gallery.subtitle}
          </p>
        </div>

        {/* Category filter */}
        <div className="flex flex-wrap gap-1 text-xs">
          <button
            type="button"
            onClick={() => setCategory('')}
            className={`px-2.5 py-1 rounded border transition-colors ${
              category === ''
                ? 'bg-[var(--brand-navy)] text-white border-[var(--brand-navy)]'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border-muted)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {t.gallery.filterAll}
          </button>
          <button
            type="button"
            onClick={() => setCategory('infrastructure')}
            className={`px-2.5 py-1 rounded border transition-colors ${
              category === 'infrastructure'
                ? 'bg-[var(--brand-navy)] text-white border-[var(--brand-navy)]'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border-muted)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {t.gallery.filterInfra}
          </button>
          <button
            type="button"
            onClick={() => setCategory('gram_sabha')}
            className={`px-2.5 py-1 rounded border transition-colors ${
              category === 'gram_sabha'
                ? 'bg-[var(--brand-navy)] text-white border-[var(--brand-navy)]'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border-muted)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {t.gallery.filterGramSabha}
          </button>
        </div>
      </header>

      <Alert severity="info" title={t.gallery.policyTitle}>
        <p>{t.gallery.policyDesc}</p>
      </Alert>

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : albums.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 w-full">
          {albums.map((album) => {
            const categoryLabel = getCategoryLabel(album.category_display, language);
            const photoCount = album.item_count ?? album.photo_count ?? 0;
            const photoCountText = `${photoCount} ${language === 'mr' ? 'छायाचित्रे' : 'Photos'}`;

            return (
              <article
                key={album.id}
                onClick={() => handleOpenAlbum(album)}
                className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl shadow-xs hover:shadow-md hover:border-[var(--brand-navy)]/40 transition-all duration-200 overflow-hidden flex flex-col h-full group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-navy)]"
                role="button"
                tabIndex={0}
                aria-label={`${album.title} - ${photoCountText}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleOpenAlbum(album);
                  }
                }}
              >
                {/* Card Header & Content */}
                <div className="p-5 flex-1 flex flex-col">
                  {/* Top Row: Category Badge & Optional Event Date */}
                  <div className="flex items-center justify-between gap-2 mb-2.5">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-blue-50 text-[var(--brand-navy)] border border-blue-200/80 shadow-2xs">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--brand-navy)]" aria-hidden="true" />
                      {categoryLabel}
                    </span>
                    {album.event_date && (
                      <span className="text-[11px] text-[var(--text-muted)] font-medium flex items-center gap-1 shrink-0">
                        <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        <time dateTime={album.event_date}>
                          {formatAlbumDate(album.event_date, language)}
                        </time>
                      </span>
                    )}
                  </div>

                  {/* Album Title (Full Width) */}
                  <h3 className="text-base sm:text-lg font-bold text-[var(--text-primary)] leading-snug group-hover:text-[var(--brand-navy)] transition-colors">
                    {album.title}
                  </h3>

                  {/* Category & Photo Count Metadata */}
                  <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-1.5">
                    <span className="font-medium">{categoryLabel}</span>
                    <span className="text-slate-300 dark:text-slate-600" aria-hidden="true">•</span>
                    <span>{photoCountText}</span>
                  </div>

                  {/* Album Description */}
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2 leading-relaxed mt-2.5 mb-4">
                    {album.description || t.placeholders.officialVerificationPending}
                  </p>

                  {/* Thumbnail Image: 16:9 Aspect Ratio with Bottom Gradient Caption */}
                  <div className="mt-auto pt-1">
                    {album.cover_image?.image_url ? (
                      <div className="w-full aspect-video rounded-lg bg-slate-900 overflow-hidden relative border border-[var(--border-muted)] shadow-inner group-hover:border-blue-300 transition-colors">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={resolveMediaUrl(album.cover_image.image_url)}
                          alt={album.cover_image.alt_text || album.cover_image.caption || album.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                          loading="lazy"
                        />
                        {album.cover_image.caption && (
                          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/45 to-transparent text-white text-[11px] font-medium px-3 pt-6 pb-2 truncate">
                            {album.cover_image.caption}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="w-full aspect-video rounded-lg bg-[var(--bg-muted)] border border-dashed border-[var(--border-primary)] flex flex-col items-center justify-center text-[var(--text-muted)] p-4 text-center">
                        <span className="text-3xl mb-1" aria-hidden="true">🖼️</span>
                        <span className="text-[11px] font-medium">
                          {t.placeholders.officialVerificationPending}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Distinct Card Footer */}
                <footer className="px-5 py-3.5 bg-[var(--bg-muted)]/60 border-t border-[var(--border-muted)] flex items-center justify-between text-xs mt-auto">
                  <span className="inline-flex items-center gap-1.5 font-bold text-[var(--brand-navy)] group-hover:text-blue-700 transition-colors">
                    <span>
                      {loadingAlbumId === album.id
                        ? t.common.loading
                        : language === 'mr'
                        ? 'छायाचित्रे पहा'
                        : 'View Photos'}
                    </span>
                    <span aria-hidden="true" className="group-hover:translate-x-1 transition-transform">&rarr;</span>
                  </span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium text-[var(--text-muted)] bg-[var(--bg-surface)] border border-[var(--border-muted)] shadow-2xs">
                    {photoCountText}
                  </span>
                </footer>
              </article>
            );
          })}
        </div>
      ) : (
        <PlaceholderNotice
          title={t.gallery.emptyTitle}
          description={t.gallery.emptyDesc}
        />
      )}

      {/* Accessible Interactive Lightbox Modal */}
      {selectedAlbum && lightboxIndex !== null && currentPhoto && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/90 backdrop-blur-md flex flex-col items-center justify-between p-3 sm:p-6 text-white"
          role="dialog"
          aria-modal="true"
          aria-label={selectedAlbum.title}
        >
          {/* Top Bar: Title, Counter & Close */}
          <div className="w-full max-w-5xl flex items-center justify-between gap-4 border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                <span>🖼️</span>
                <span>{selectedAlbum.title}</span>
              </h2>
              <p className="text-[11px] text-slate-400">
                {selectedAlbum.category_display}
              </p>
            </div>

            <div className="flex items-center gap-4">
              <span className="text-xs font-mono font-semibold px-2.5 py-1 bg-slate-800 text-slate-300 rounded border border-slate-700">
                {lightboxIndex + 1} / {selectedAlbum.photos.length}
              </span>
              <button
                type="button"
                onClick={() => setLightboxIndex(null)}
                aria-label="Close Lightbox (Escape)"
                className="text-slate-400 hover:text-white text-xl font-bold p-1 rounded hover:bg-slate-800 transition-colors"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Main Photo Display with Navigation Arrows */}
          <div className="relative w-full max-w-5xl flex-1 flex items-center justify-center py-2 sm:py-4 overflow-hidden">
            {/* Previous Button */}
            <button
              type="button"
              onClick={() =>
                setLightboxIndex((prev) =>
                  prev !== null && prev > 0 ? prev - 1 : selectedAlbum.photos.length - 1
                )
              }
              aria-label="Previous Photo (Left Arrow)"
              className="absolute left-1 sm:left-3 z-10 p-2.5 sm:p-3 rounded-full bg-slate-900/80 hover:bg-slate-800 text-white border border-slate-700 transition-all shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              &#10094;
            </button>

            {/* Photo view */}
            <div className="max-h-[68vh] max-w-full flex flex-col items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={resolveMediaUrl(currentPhoto.image_url)}
                alt={currentPhoto.alt_text || currentPhoto.caption || selectedAlbum.title}
                className="max-h-[64vh] max-w-full object-contain rounded-lg shadow-2xl border border-slate-800"
              />
            </div>

            {/* Next Button */}
            <button
              type="button"
              onClick={() =>
                setLightboxIndex((prev) =>
                  prev !== null && prev < selectedAlbum.photos.length - 1 ? prev + 1 : 0
                )
              }
              aria-label="Next Photo (Right Arrow)"
              className="absolute right-1 sm:right-3 z-10 p-2.5 sm:p-3 rounded-full bg-slate-900/80 hover:bg-slate-800 text-white border border-slate-700 transition-all shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              &#10095;
            </button>
          </div>

          {/* Bottom Bar: Caption & Thumbnails Strip */}
          <div className="w-full max-w-5xl space-y-2 pt-2 border-t border-slate-800">
            {currentPhoto.caption && (
              <p className="text-center text-xs sm:text-sm font-medium text-slate-200">
                {currentPhoto.caption}
              </p>
            )}

            {/* Thumbnails strip */}
            <div className="flex items-center justify-center gap-2 overflow-x-auto py-1 max-w-full">
              {selectedAlbum.photos.map((photo, idx) => (
                <button
                  key={photo.id}
                  type="button"
                  onClick={() => setLightboxIndex(idx)}
                  className={`w-12 h-12 rounded overflow-hidden shrink-0 border-2 transition-all ${
                    idx === lightboxIndex
                      ? 'border-blue-500 scale-105 shadow-md'
                      : 'border-slate-800 opacity-60 hover:opacity-100'
                  }`}
                  aria-label={`Photo ${idx + 1}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={resolveMediaUrl(photo.image_url)}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
