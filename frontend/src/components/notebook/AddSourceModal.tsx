import React, { useState } from 'react';
import { Upload, Link, FileText, X } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { useCreateSource } from '../../hooks/useSources';

interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  notebookName: string;
}

export function AddSourceModal({ isOpen, onClose, notebookName }: AddSourceModalProps) {
  const [sourceType, setSourceType] = useState<'text' | 'link' | 'upload'>('text');
  const [formData, setFormData] = useState({
    content: '',
    url: '',
    file: null as File | null,
    applyTransformations: '',
    embed: true,
  });

  const createSource = useCreateSource();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const data = new FormData();
    data.append('type', sourceType);
    data.append('embed', formData.embed.toString());
    
    if (formData.applyTransformations) {
      data.append('apply_transformations', formData.applyTransformations);
    }

    switch (sourceType) {
      case 'text':
        if (!formData.content.trim()) return;
        data.append('content', formData.content);
        break;
      case 'link':
        if (!formData.url.trim()) return;
        data.append('url', formData.url);
        break;
      case 'upload':
        if (!formData.file) return;
        data.append('file', formData.file);
        break;
    }

    try {
      await createSource.mutateAsync({
        notebookName,
        data,
      });
      
      // Reset form and close modal
      setFormData({
        content: '',
        url: '',
        file: null,
        applyTransformations: '',
        embed: true,
      });
      setSourceType('text');
      onClose();
    } catch (error) {
      console.error('Failed to create source:', error);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFormData({ ...formData, file });
    }
  };

  const sourceTypes = [
    {
      type: 'text' as const,
      icon: FileText,
      label: 'Text',
      description: 'Add text content directly',
    },
    {
      type: 'link' as const,
      icon: Link,
      label: 'Link',
      description: 'Add content from a URL',
    },
    {
      type: 'upload' as const,
      icon: Upload,
      label: 'Upload',
      description: 'Upload a file (PDF, DOCX, etc.)',
    },
  ];

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Source" size="lg">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Source Type Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Source Type
          </label>
          <div className="grid grid-cols-3 gap-3">
            {sourceTypes.map(({ type, icon: Icon, label, description }) => (
              <button
                key={type}
                type="button"
                onClick={() => setSourceType(type)}
                className={`p-4 border rounded-lg text-left transition-colors ${
                  sourceType === type
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <Icon className={`h-6 w-6 mb-2 ${
                  sourceType === type ? 'text-primary-600' : 'text-gray-400'
                }`} />
                <div className="font-medium text-sm">{label}</div>
                <div className="text-xs text-gray-500 mt-1">{description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Source Content */}
        <div>
          {sourceType === 'text' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Text Content
              </label>
              <textarea
                value={formData.content}
                onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                rows={8}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="Enter your text content here..."
                required
              />
            </div>
          )}

          {sourceType === 'link' && (
            <Input
              label="URL"
              type="url"
              value={formData.url}
              onChange={(e) => setFormData({ ...formData, url: e.target.value })}
              placeholder="https://example.com"
              required
            />
          )}

          {sourceType === 'upload' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                File Upload
              </label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
                <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                <div className="text-sm text-gray-600 mb-2">
                  {formData.file ? formData.file.name : 'Choose a file to upload'}
                </div>
                <input
                  type="file"
                  onChange={handleFileChange}
                  accept=".pdf,.docx,.doc,.txt,.md"
                  className="hidden"
                  id="file-upload"
                  required
                />
                <label
                  htmlFor="file-upload"
                  className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 cursor-pointer"
                >
                  Select File
                </label>
                {formData.file && (
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, file: null })}
                    className="ml-2 text-red-600 hover:text-red-800"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Supported formats: PDF, DOCX, DOC, TXT, MD
              </p>
            </div>
          )}
        </div>

        {/* Options */}
        <div className="space-y-4">
          <Input
            label="Apply Transformations"
            value={formData.applyTransformations}
            onChange={(e) => setFormData({ ...formData, applyTransformations: e.target.value })}
            placeholder="transformation1, transformation2"
            helperText="Comma-separated list of transformation names (optional)"
          />

          <div className="flex items-center">
            <input
              type="checkbox"
              id="embed"
              checked={formData.embed}
              onChange={(e) => setFormData({ ...formData, embed: e.target.checked })}
              className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
            />
            <label htmlFor="embed" className="ml-2 block text-sm text-gray-700">
              Enable vector search (embed content)
            </label>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={createSource.isPending}>
            Add Source
          </Button>
        </div>
      </form>
    </Modal>
  );
}