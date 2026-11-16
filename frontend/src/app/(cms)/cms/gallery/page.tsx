'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import { useAuth } from '@/context/AuthContext';
import {
  fetchCmsGallery,
  createCmsGalleryAlbum,
  updateCmsGalleryAlbum,
  uploadCmsGalleryImage,
  addCmsGalleryImageLink,
  fetchCmsGalleryAlbumDetail,
  reorderCmsGalleryItems,
  setCoverCmsGalleryImage,
  deleteCmsGalleryItem,
  executeGovernanceAction,
  resolveMediaUrl,
} from '@/lib/api';
import type { CmsGalleryItem, CmsGalleryPhoto, CmsGalleryAlbumDetail } from '@/lib/types';

export default function CmsGalleryPage() {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.role === 'super_admin');

  const [albums, setAlbums] = useState<CmsGalleryItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddPhotoModal, setShowAddPhotoModal] = useState(false);
  const [editingAlbum, setEditingAlbum] = useState<CmsGalleryItem | null>(null);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(null);
  const [managingAlbum, setManagingAlbum] = useState<CmsGalleryAlbumDetail | null>(null);
  const [managingLoading, setManagingLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Create album form states (Single title and description)
  const [slug, setSlug] = useState('');
  const [category, setCategory] = useState('infrastructure');
  const [eventDate, setEventDate] = useState('');
  const [primaryLanguage, setPrimaryLanguage] = useState<'mr' | 'hi' | 'en'>('mr');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [publishNow, setPublishNow] = useState(false);
  const [submittingAlbum, setSubmittingAlbum] = useState(false);

  // Edit album form states (Single title and description)
  const [editCategory, setEditCategory] = useState('infrastructure');
  const [editEventDate, setEditEventDate] = useState('');
  const [editPrimaryLanguage, setEditPrimaryLanguage] = useState<'mr' | 'hi' | 'en'>('mr');
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  // Add image form states (Single caption and alt text)
  const [sourceType, setSourceType] = useState<'upload' | 'link'>('upload');
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [externalUrl, setExternalUrl] = useState('');
  const [caption, setCaption] = useState('');
  const [altText, setAltText] = useState('');
  const [submittingPhoto, setSubmittingPhoto] = useState(false);

  async function loadAlbums() {
    setLoading(true);
    try {
      const res = await fetchCmsGallery();
      if (res) {
        setAlbums(res.results);
      }
    } catch (err) {
      console.error('Failed to load gallery albums', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAlbums();
  }, []);

  async function openManagePhotos(albumId: string) {
    setManagingLoading(true);
    setManagingAlbum(null);
    try {
      const res = await fetchCmsGalleryAlbumDetail(albumId);
      if (res) {
        setManagingAlbum(res);
      }
    } catch (err) {
      console.error('Failed to load album photos', err);
    } finally {
      setManagingLoading(false);
    }
  }

  function openAddPhotoModal(albumId: string) {
    setSelectedAlbumId(albumId);
    setSourceType('upload');
    setImageFile(null);
    setImagePreviewUrl(null);
    setExternalUrl('');
    setCaption('');
    setAltText('');
    setShowAddPhotoModal(true);
    setFeedback(null);
  }

  function openCreateModal() {
    setSlug('');
    setCategory('infrastructure');
    setEventDate('');
    setPrimaryLanguage('mr');
    setTitle('');
    setDescription('');
    setPublishNow(false);
    setFeedback(null);
    setShowCreateModal(true);
  }

  function openEditModal(alb: CmsGalleryItem) {
    setEditingAlbum(alb);
    const primLang = (alb.primary_language || 'mr') as 'mr' | 'hi' | 'en';
    setEditPrimaryLanguage(primLang);
    setEditCategory(alb.category);
    setEditEventDate(alb.event_date ? alb.event_date.slice(0, 10) : '');
    setEditTitle(alb.title || alb.translations?.[0]?.title || '');
    setEditDescription(alb.description || alb.translations?.[0]?.description || '');
    setFeedback(null);
  }

  async function handleCreateAlbum(e: React.FormEvent) {
    e.preventDefault();
    if (!slug.trim()) {
      setFeedback({ type: 'error', message: 'अल्बम स्लग आवश्यक आहे (Slug is required).' });
      return;
    }

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setFeedback({
        type: 'error',
        message: 'अल्बम शीर्षक आवश्यक आहे (Album title is required).',
      });
      return;
    }

    setSubmittingAlbum(true);
    setFeedback(null);

    const res = await createCmsGalleryAlbum({
      slug: slug.trim(),
      title: trimmedTitle,
      description: description.trim() || undefined,
      category,
      event_date: eventDate || undefined,
      primary_language: primaryLanguage,
      language_code: primaryLanguage,
    });

    if (res.success && res.album_id && publishNow && isSuperAdmin) {
      // Super Admin direct publish
      const pubRes = await executeGovernanceAction({
        entity_type: 'gallery',
        action: 'publish',
        target_id: res.album_id,
        justification: 'Direct publication by Super Administrator upon creation',
      });
      setSubmittingAlbum(false);
      if (pubRes.success) {
        setFeedback({ type: 'success', message: 'अल्बम तयार करून थेट प्रकाशित करण्यात आला (Album created and published directly).' });
        setShowCreateModal(false);
        loadAlbums();
      } else {
        setFeedback({ type: 'error', message: `अल्बम तयार झाला परंतु प्रकाशन अयशस्वी: ${pubRes.error}` });
        setShowCreateModal(false);
        loadAlbums();
      }
    } else if (res.success) {
      setSubmittingAlbum(false);
      setFeedback({ type: 'success', message: 'अल्बम मसुदा यशस्वीरीत्या जतन केला (Draft album created successfully).' });
      setShowCreateModal(false);
      loadAlbums();
    } else {
      setSubmittingAlbum(false);
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleSaveEditAlbum(e: React.FormEvent) {
    e.preventDefault();
    if (!editingAlbum) return;

    const trimmedTitle = editTitle.trim();
    if (!trimmedTitle) {
      setFeedback({
        type: 'error',
        message: 'अल्बम शीर्षक आवश्यक आहे (Album title cannot be empty).',
      });
      return;
    }

    setSavingEdit(true);
    setFeedback(null);

    const res = await updateCmsGalleryAlbum(editingAlbum.id, {
      category: editCategory,
      event_date: editEventDate || null,
      primary_language: editPrimaryLanguage,
      language_code: editPrimaryLanguage,
      title: trimmedTitle,
      description: editDescription.trim(),
    });

    setSavingEdit(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'अल्बम माहिती यशस्वीरीत्या अद्यतनित केली (Album details updated successfully).' });
      setEditingAlbum(null);
      loadAlbums();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to update album.' });
    }
  }

  async function handleAddPhoto(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAlbumId) return;

    const trimmedAltText = altText.trim() || caption.trim() || 'छायाचित्र';
    if (trimmedAltText.length < 3) {
      setFeedback({
        type: 'error',
        message: 'वर्णनात्मक मजकूर (Alt text) किमान ३ अक्षरांचा असणे अनिवार्य आहे.',
      });
      return;
    }

    setSubmittingPhoto(true);
    setFeedback(null);

    let res: { success: boolean; error?: string };

    if (sourceType === 'upload') {
      if (!imageFile) {
        setFeedback({ type: 'error', message: t.cmsGallery.selectFile });
        setSubmittingPhoto(false);
        return;
      }
      const formData = new FormData();
      formData.append('image_file', imageFile);
      formData.append('source_type', 'upload');
      formData.append('caption', caption.trim());
      formData.append('alt_text', trimmedAltText);

      res = await uploadCmsGalleryImage(selectedAlbumId, formData);
    } else {
      if (!externalUrl.trim()) {
        setFeedback({ type: 'error', message: 'External image or Google Drive URL is required.' });
        setSubmittingPhoto(false);
        return;
      }
      res = await addCmsGalleryImageLink(selectedAlbumId, {
        external_url: externalUrl.trim(),
        caption: caption.trim(),
        alt_text: trimmedAltText,
      });
    }

    setSubmittingPhoto(false);

    if (res.success) {
      setFeedback({
        type: 'success',
        message: sourceType === 'upload' ? 'Photograph uploaded to album.' : 'Image link successfully added to album.',
      });
      setShowAddPhotoModal(false);
      setImageFile(null);
      setImagePreviewUrl(null);
      setExternalUrl('');
      setCaption('');
      setAltText('');
      loadAlbums();
      if (managingAlbum && managingAlbum.id === selectedAlbumId) {
        openManagePhotos(selectedAlbumId);
      }
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleMovePhoto(photoIndex: number, direction: 'up' | 'down') {
    if (!managingAlbum || !managingAlbum.items) return;
    const items = [...managingAlbum.items];
    const targetIndex = direction === 'up' ? photoIndex - 1 : photoIndex + 1;
    if (targetIndex < 0 || targetIndex >= items.length) return;

    // Swap items
    const temp = items[photoIndex];
    items[photoIndex] = items[targetIndex];
    items[targetIndex] = temp;

    const itemIds = items.map((it) => it.id);
    const res = await reorderCmsGalleryItems(managingAlbum.id, itemIds);
    if (res.success) {
      openManagePhotos(managingAlbum.id);
    } else {
      alert(res.error || 'Failed to reorder photos.');
    }
  }

  async function handleSetCover(photoId: string) {
    if (!managingAlbum) return;
    const res = await setCoverCmsGalleryImage(managingAlbum.id, photoId);
    if (res.success) {
      openManagePhotos(managingAlbum.id);
      loadAlbums();
    } else {
      alert(res.error || 'Failed to set cover image.');
    }
  }

  async function handleDeletePhoto(photoId: string) {
    if (!managingAlbum) return;
    if (!window.confirm('हे छायाचित्र अल्बममधून कायमचे हटवायचे आहे का? (Delete this photo?)')) return;
    const res = await deleteCmsGalleryItem(managingAlbum.id, photoId);
    if (res.success) {
      openManagePhotos(managingAlbum.id);
      loadAlbums();
    } else {
      alert(res.error || 'Failed to delete photo.');
    }
  }

  async function handleSubmitForReview(albumId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'gallery',
      action: 'submit',
      target_id: albumId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsGallery.submitAlbum });
      loadAlbums();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handlePublish(albumId: string) {
    const promptMsg = t.governance.justificationMinLength;
    const just = window.prompt(promptMsg);
    if (!just || just.trim().length < 10) {
      alert(t.governance.justificationMinLength);
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'gallery',
      action: 'publish',
      target_id: albumId,
      justification: just.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsGallery.publishAlbum });
      loadAlbums();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleWithdraw(albumId: string) {
    const promptMsg = t.governance.justificationMinLength;
    const just = window.prompt(promptMsg);
    if (!just || just.trim().length < 10) {
      alert(t.governance.justificationMinLength);
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'gallery',
      action: 'withdraw',
      target_id: albumId,
      justification: just.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.withdraw });
      loadAlbums();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">🖼️</span>
            <span>{t.cmsGallery.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.cmsGallery.pageSubtitle}
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsGallery.createAlbum}</span>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <Alert
          severity={feedback.type === 'success' ? 'info' : 'danger'}
          title={feedback.type === 'success' ? t.common.save : t.governance.actionFailed}
        >
          <p>{feedback.message}</p>
        </Alert>
      )}

      {/* Albums List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.common.loading}
          </div>
        ) : albums.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {t.cmsGallery.emptyList}
          </div>
        ) : (
          albums.map((alb) => {
            const primLang = alb.primary_language || 'mr';
            const albumTitle = alb.title || alb.translations?.[0]?.title || alb.slug;
            const albumDesc = alb.description || alb.translations?.[0]?.description;

            return (
              <div key={alb.id} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded font-bold">
                      /{alb.slug}
                    </span>
                    <Badge variant="primary">{alb.category.toUpperCase()}</Badge>
                    <Badge
                      variant={
                        alb.status === 'published'
                          ? 'success'
                          : alb.status === 'withdrawn'
                          ? 'neutral'
                          : 'warning'
                      }
                    >
                      {alb.status}
                    </Badge>

                    {/* Single Primary Language Badge */}
                    <span className="px-1.5 py-0.5 text-[10px] bg-blue-100 text-blue-900 border border-blue-300 rounded font-bold">
                      प्राथमिक: {primLang.toUpperCase()}
                    </span>

                    <span className="text-xs text-slate-600 font-semibold">
                      {t.cmsGallery.photoCount}: {alb.items_count}
                    </span>
                    {alb.event_date && (
                      <span className="text-xs text-slate-500">
                        {t.cmsGallery.eventDate}: {alb.event_date}
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
                    {/* Edit Album Button */}
                    <button
                      onClick={() => openEditModal(alb)}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1"
                      title="Edit album title, description and details"
                    >
                      <span>✏️</span>
                      <span>संपादित करा (Edit)</span>
                    </button>

                    {/* Manage Photos Button */}
                    <button
                      onClick={() => openManagePhotos(alb.id)}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1"
                    >
                      <span>🔍</span>
                      <span>छायाचित्रे व्यवस्थापित करा</span>
                    </button>

                    {/* Add Photo Button */}
                    <button
                      onClick={() => openAddPhotoModal(alb.id)}
                      className="px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-[#1e3a8a] border border-blue-200 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1"
                    >
                      <span aria-hidden="true">+</span>
                      <span>{t.cmsGallery.uploadPhoto}</span>
                    </button>

                    {/* Role-governed Workflow Actions */}
                    {isSuperAdmin ? (
                      // Super Admin Direct Publish Controls
                      <>
                        {(alb.status === 'draft' || alb.status === 'submitted') && (
                          <button
                            onClick={() => handlePublish(alb.id)}
                            className="px-2.5 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                          >
                            <span>🚀</span>
                            <span>थेट प्रकाशित करा (Publish Directly)</span>
                          </button>
                        )}
                        {alb.status === 'approved' && (
                          <button
                            onClick={() => handlePublish(alb.id)}
                            className="px-2.5 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold shadow-sm transition-colors"
                          >
                            {t.cmsGallery.publishAlbum}
                          </button>
                        )}
                      </>
                    ) : (
                      // Operator Review Workflow Controls
                      <>
                        {alb.status === 'draft' && (
                          <button
                            onClick={() => handleSubmitForReview(alb.id)}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold shadow-sm transition-colors"
                          >
                            {t.cmsGallery.submitAlbum}
                          </button>
                        )}
                        {alb.status === 'submitted' && (
                          <span className="px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-300 rounded text-xs font-medium">
                            पुनरावलोकनासाठी प्रलंबित (Under Review)
                          </span>
                        )}
                      </>
                    )}

                    {alb.status === 'published' && (
                      <>
                        <button
                          onClick={() => handleWithdraw(alb.id)}
                          className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 rounded text-xs font-medium transition-colors"
                        >
                          {t.governance.withdraw}
                        </button>
                        <a
                          href="/gallery"
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 bg-slate-50 hover:bg-slate-100 text-slate-700 border border-slate-300 rounded text-xs font-medium transition-colors inline-flex items-center gap-1"
                        >
                          <span>सार्वजनिक पहा &rarr;</span>
                        </a>
                      </>
                    )}
                  </div>
                </div>

                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-slate-900">
                    {albumTitle}
                  </h4>
                  {albumDesc && (
                    <p className="text-xs text-slate-600 line-clamp-2">
                      {albumDesc}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Album Photos Management Modal */}
      {managingAlbum && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-4xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>🖼️</span>
                  <span>अल्बम छायाचित्रे व्यवस्थापन (Album Photos & Ordering)</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5 font-mono">
                  /{managingAlbum.slug} ({managingAlbum.items?.length || 0} छायाचित्रे)
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => openAddPhotoModal(managingAlbum.id)}
                  className="px-3 py-1.5 bg-[#1e3a8a] text-white hover:bg-blue-900 rounded-lg text-xs font-semibold transition-colors inline-flex items-center gap-1"
                >
                  <span>+</span>
                  <span>नवीन फोटो जोडा (Add Photo)</span>
                </button>
                <button
                  onClick={() => setManagingAlbum(null)}
                  aria-label="Close"
                  className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
                >
                  ✕
                </button>
              </div>
            </div>

            {managingAlbum.items?.length === 0 ? (
              <div className="p-8 text-center bg-slate-50 border border-dashed border-slate-300 rounded-lg text-slate-600 text-xs space-y-2">
                <span className="text-3xl block">📷</span>
                <p className="font-semibold text-slate-800">या अल्बममध्ये अद्याप छायाचित्रे जोडलेली नाहीत.</p>
                <button
                  type="button"
                  onClick={() => openAddPhotoModal(managingAlbum.id)}
                  className="px-3 py-1.5 bg-[#1e3a8a] text-white hover:bg-blue-900 rounded-lg text-xs font-semibold mt-2 inline-flex items-center gap-1"
                >
                  <span>+</span>
                  <span>पहिले छायाचित्र जोडा (Add First Photo)</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {managingAlbum.items.map((photo, idx) => {
                  const photoCaption = photo.caption || photo.caption_mr || photo.original_filename;
                  const photoAlt = photo.alt_text || photo.alt_text_mr || '';

                  return (
                    <div
                      key={photo.id}
                      className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between space-y-2 hover:border-slate-300 transition-all text-xs"
                    >
                      <div className="space-y-1.5">
                        <div className="aspect-video rounded bg-slate-200 overflow-hidden relative border border-slate-300">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={resolveMediaUrl(photo.preview_url || photo.image_url)}
                            alt={photoAlt || photoCaption || 'Gallery Photo'}
                            className="w-full h-full object-cover"
                          />
                          {photo.is_cover_image && (
                            <div className="absolute top-1 right-1 bg-amber-500 text-white font-bold text-[10px] px-2 py-0.5 rounded shadow">
                              ⭐ कव्हर फोटो
                            </div>
                          )}
                          <div className="absolute bottom-1 left-1 bg-slate-900/80 text-white font-mono text-[10px] px-1.5 py-0.5 rounded">
                            #{photo.display_order} • {photo.source_type.toUpperCase()}
                          </div>
                        </div>

                        <div className="space-y-0.5">
                          <div className="font-semibold text-slate-900 truncate" title={photoCaption}>
                            {photoCaption}
                          </div>
                          {photoAlt && (
                            <div className="text-[11px] text-slate-500 truncate" title={photoAlt}>
                              Alt: {photoAlt}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Photo Action Controls */}
                      <div className="flex flex-wrap items-center justify-between gap-1 pt-2 border-t border-slate-200 text-[11px]">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            disabled={idx === 0}
                            onClick={() => handleMovePhoto(idx, 'up')}
                            className="px-2 py-0.5 bg-white border border-slate-300 hover:bg-slate-100 disabled:opacity-30 rounded font-bold"
                            title="क्रम वर हलवा (Move Up)"
                          >
                            ⬆
                          </button>
                          <button
                            type="button"
                            disabled={idx === managingAlbum.items.length - 1}
                            onClick={() => handleMovePhoto(idx, 'down')}
                            className="px-2 py-0.5 bg-white border border-slate-300 hover:bg-slate-100 disabled:opacity-30 rounded font-bold"
                            title="क्रम खाली हलवा (Move Down)"
                          >
                            ⬇
                          </button>
                        </div>

                        <div className="flex items-center gap-1">
                          {!photo.is_cover_image && (
                            <button
                              type="button"
                              onClick={() => handleSetCover(photo.id)}
                              className="px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-300 hover:bg-amber-100 rounded font-medium"
                              title="मुख्य कव्हर म्हणून सेट करा"
                            >
                              ⭐ कव्हर
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDeletePhoto(photo.id)}
                            className="px-2 py-0.5 bg-rose-50 text-rose-700 border border-rose-300 hover:bg-rose-100 rounded font-medium"
                            title="हटवा (Delete)"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex justify-end pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setManagingAlbum(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold"
              >
                {t.common.close}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Album Modal (Exactly ONE title and ONE description field) */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span aria-hidden="true">🖼️</span>
                  <span>{t.cmsGallery.createAlbum}</span>
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  नवीन छायाचित्र अल्बम तयार करा (Create Album)
                </p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateAlbum} className="space-y-4 text-xs">
              {feedback && feedback.type === 'error' && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-2">
                  <span>⚠️</span>
                  <span>{feedback.message}</span>
                </div>
              )}

              {/* Slug and Date */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsGallery.slug} * (ASCII):
                  </label>
                  <input
                    type="text"
                    required
                    value={slug}
                    onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                    placeholder="panchayat-building-inauguration"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 font-mono focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsGallery.eventDate}:
                  </label>
                  <input
                    type="date"
                    value={eventDate}
                    onChange={(e) => setEventDate(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              {/* Category */}
              <div>
                <label htmlFor="album-category-select" className="block text-slate-700 font-semibold mb-1">
                  {t.cmsGallery.category}:
                </label>
                <select
                  id="album-category-select"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                >
                  <option value="infrastructure">पायाभूत सुविधा व विकासकामे (Infrastructure)</option>
                  <option value="gram_sabha">ग्रामसभा व बैठका (Gram Sabha)</option>
                  <option value="welfare">योजना वाटप व समाजकल्याण (Welfare)</option>
                  <option value="cultural">सांस्कृतिक व राष्ट्रीय उत्सव (Cultural)</option>
                  <option value="environment">पर्यावरण व जलसंधारण (Environment)</option>
                </select>
              </div>

              {/* Single Primary Language Selection */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  प्राथमिक भाषा (Primary Language) *:
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPrimaryLanguage('mr')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      primaryLanguage === 'mr'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    मराठी (MR)
                  </button>
                  <button
                    type="button"
                    onClick={() => setPrimaryLanguage('hi')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      primaryLanguage === 'hi'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    हिंदी (HI)
                  </button>
                  <button
                    type="button"
                    onClick={() => setPrimaryLanguage('en')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      primaryLanguage === 'en'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    English (EN)
                  </button>
                </div>
              </div>

              {/* Exactly ONE Title Field */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsGallery.albumTitle} * ({primaryLanguage === 'mr' ? 'मराठी' : primaryLanguage === 'hi' ? 'हिंदी' : 'English'}):
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={
                    primaryLanguage === 'en'
                      ? 'e.g. Gram Panchayat New Administrative Building Inauguration'
                      : primaryLanguage === 'hi'
                      ? 'उदा. ग्राम पंचायत नवीन प्रशासनिक भवन लोकार्पण समारोह'
                      : 'उदा. ग्रामपंचायत नूतन प्रशासकीय इमारत लोकार्पण सोहळा'
                  }
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Exactly ONE Description Field */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsGallery.description} ({primaryLanguage === 'mr' ? 'मराठी' : primaryLanguage === 'hi' ? 'हिंदी' : 'English'}):
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={
                    primaryLanguage === 'en'
                      ? 'Brief summary of the ceremony...'
                      : primaryLanguage === 'hi'
                      ? 'समारोह का संक्षिप्त विवरण...'
                      : 'सोहळ्याची संक्षिप्त माहिती...'
                  }
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Super Admin Direct Publish Checkbox */}
              {isSuperAdmin && (
                <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-lg flex items-start gap-2">
                  <input
                    type="checkbox"
                    id="album-publish-now"
                    checked={publishNow}
                    onChange={(e) => setPublishNow(e.target.checked)}
                    className="mt-0.5 rounded text-blue-800 focus:ring-blue-700"
                  />
                  <label htmlFor="album-publish-now" className="text-xs text-slate-800 cursor-pointer">
                    <strong className="block text-[#1e3a8a]">थेट प्रकाशित करा (Publish Directly upon creation)</strong>
                    <span className="text-[11px] text-slate-600">
                      मुख्य प्रशासक अधिकार: हा अल्बम पुनरावलोकन प्रक्रियेविना थेट प्रकाशित केला जाईल (छायाचित्र आवश्यक).
                    </span>
                  </label>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={submittingAlbum}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submittingAlbum ? t.common.loading : publishNow ? 'तयार करून थेट प्रकाशित करा' : t.common.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Album Modal (Exactly ONE title and ONE description field) */}
      {editingAlbum && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>✏️</span>
                  <span>अल्बम संपादन (Edit Album)</span>
                </h3>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  /{editingAlbum.slug}
                </p>
              </div>
              <button
                onClick={() => setEditingAlbum(null)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveEditAlbum} className="space-y-4 text-xs">
              {/* Category & Date */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="edit-album-category-select" className="block text-slate-700 font-semibold mb-1">
                    {t.cmsGallery.category}:
                  </label>
                  <select
                    id="edit-album-category-select"
                    value={editCategory}
                    onChange={(e) => setEditCategory(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="infrastructure">पायाभूत सुविधा व विकासकामे (Infrastructure)</option>
                    <option value="gram_sabha">ग्रामसभा व बैठका (Gram Sabha)</option>
                    <option value="welfare">योजना वाटप व समाजकल्याण (Welfare)</option>
                    <option value="cultural">सांस्कृतिक व राष्ट्रीय उत्सव (Cultural)</option>
                    <option value="environment">पर्यावरण व जलसंधारण (Environment)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsGallery.eventDate}:
                  </label>
                  <input
                    type="date"
                    value={editEventDate}
                    onChange={(e) => setEditEventDate(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              {/* Primary Language Selection */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  प्राथमिक भाषा (Primary Language) *:
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setEditPrimaryLanguage('mr')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      editPrimaryLanguage === 'mr'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    मराठी (MR)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditPrimaryLanguage('hi')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      editPrimaryLanguage === 'hi'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    हिंदी (HI)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditPrimaryLanguage('en')}
                    className={`flex-1 py-1.5 px-3 rounded-lg font-semibold text-xs border transition-all ${
                      editPrimaryLanguage === 'en'
                        ? 'bg-[#1e3a8a] text-white border-blue-900 shadow-xs'
                        : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'
                    }`}
                  >
                    English (EN)
                  </button>
                </div>
              </div>

              {/* Exactly ONE Title Field */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsGallery.albumTitle} * ({editPrimaryLanguage === 'mr' ? 'मराठी' : editPrimaryLanguage === 'hi' ? 'हिंदी' : 'English'}):
                </label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder={
                    editPrimaryLanguage === 'en'
                      ? 'e.g. Gram Panchayat New Administrative Building Inauguration'
                      : editPrimaryLanguage === 'hi'
                      ? 'उदा. ग्राम पंचायत नवीन प्रशासनिक भवन लोकार्पण समारोह'
                      : 'उदा. ग्रामपंचायत नूतन प्रशासकीय इमारत लोकार्पण सोहळा'
                  }
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Exactly ONE Description Field */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsGallery.description} ({editPrimaryLanguage === 'mr' ? 'मराठी' : editPrimaryLanguage === 'hi' ? 'हिंदी' : 'English'}):
                </label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder={
                    editPrimaryLanguage === 'en'
                      ? 'Brief summary of the ceremony...'
                      : editPrimaryLanguage === 'hi'
                      ? 'समारोह का संक्षिप्त विवरण...'
                      : 'सोहळ्याची संक्षिप्त माहिती...'
                  }
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditingAlbum(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {savingEdit ? t.common.loading : 'बदल जतन करा (Save Changes)'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Photograph Modal (Dual Source: Upload vs Link - Exactly ONE Caption and Alt Text) */}
      {showAddPhotoModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📷</span>
                <span>छायाचित्र जोडा (Add Photograph to Album)</span>
              </h3>
              <button
                onClick={() => setShowAddPhotoModal(false)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            {/* Source Type Selector Tabs */}
            <div className="flex border-b border-slate-200 pb-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => setSourceType('upload')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors flex items-center gap-1.5 ${
                  sourceType === 'upload'
                    ? 'bg-[#1e3a8a] text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                <span>📁</span>
                <span>फाईल अपलोड (Upload File)</span>
              </button>
              <button
                type="button"
                onClick={() => setSourceType('link')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors flex items-center gap-1.5 ${
                  sourceType === 'link'
                    ? 'bg-[#1e3a8a] text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                <span>🔗</span>
                <span>इमेज लिंक / Google Drive</span>
              </button>
            </div>

            <form onSubmit={handleAddPhoto} className="space-y-3 text-xs">
              {sourceType === 'upload' ? (
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsGallery.selectFile} (JPEG / PNG / WebP, max 15MB):
                  </label>
                  <input
                    type="file"
                    required
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null;
                      setImageFile(file);
                      if (file) {
                        setImagePreviewUrl(URL.createObjectURL(file));
                      } else {
                        setImagePreviewUrl(null);
                      }
                    }}
                    className="w-full text-xs text-slate-700 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:text-xs file:font-semibold file:bg-slate-100 hover:file:bg-slate-200 cursor-pointer"
                  />
                  {imagePreviewUrl && (
                    <div className="mt-2 h-36 rounded-lg bg-slate-100 border border-slate-300 overflow-hidden flex items-center justify-center">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={imagePreviewUrl}
                        alt="Preview"
                        className="max-h-full max-w-full object-contain"
                      />
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <label className="block text-slate-700 font-semibold mb-1">
                    इमेज URL किंवा Google Drive शेअर लिंक:
                  </label>
                  <input
                    type="url"
                    required
                    value={externalUrl}
                    onChange={(e) => setExternalUrl(e.target.value)}
                    placeholder="https://drive.google.com/file/d/.../view किंवा https://cdn.example.gov.in/photo.jpg"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                  <p className="text-[11px] text-slate-500 bg-blue-50 p-2 rounded border border-blue-200">
                    ℹ️ Google Drive शेअर लिंक्स थेट स्ट्रीम URL मध्ये रूपांतरित केल्या जातात. सुरक्षेसाठी खाजगी/स्थानिक IP पत्ते (SSRF) ब्लॉक केले आहेत.
                  </p>
                </div>
              )}

              {/* Accessible Alt Text (Required) */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  वर्णनात्मक मजकूर (Alt Text) * (स्क्रीन रीडर व सुलभतेसाठी अनिवार्य):
                </label>
                <input
                  type="text"
                  required
                  value={altText}
                  onChange={(e) => setAltText(e.target.value)}
                  placeholder="उदा. ग्रामपंचायत सभागृहात आयोजित ग्रामसभेचे छायाचित्र"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Exactly ONE Caption Field */}
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  छायाचित्र शीर्षक / कॅप्शन (Caption):
                </label>
                <input
                  type="text"
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder="उदा. Inauguration ceremony / सोहळ्याचे छायाचित्र"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowAddPhotoModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={submittingPhoto}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submittingPhoto ? t.common.loading : t.common.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
