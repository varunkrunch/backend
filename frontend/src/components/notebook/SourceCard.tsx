import React from 'react';
import { MoreHorizontal, ExternalLink, Trash2 } from 'lucide-react';
import { Menu } from '@headlessui/react';
import { formatRelativeTime, getSourceTypeIcon, getSourceTypeColor, truncateText } from '../../lib/utils';
import { useDeleteSource } from '../../hooks/useSources';
import type { Source } from '../../lib/api';

interface SourceCardProps {
  source: Source;
}

export function SourceCard({ source }: SourceCardProps) {
  const deleteSource = useDeleteSource();

  const handleDelete = async () => {
    if (confirm(`Are you sure you want to delete "${source.title}"?`)) {
      await deleteSource.mutateAsync(source.id);
    }
  };

  const getSourceUrl = () => {
    if (source.metadata?.url) return source.metadata.url;
    if (source.metadata?.asset?.url) return source.metadata.asset.url;
    return null;
  };

  const sourceUrl = getSourceUrl();

  return (
    <div className="card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-lg">{getSourceTypeIcon(source.type)}</span>
            <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getSourceTypeColor(source.type)}`}>
              {source.type}
            </span>
            {source.status && (
              <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                source.status === 'completed' 
                  ? 'bg-green-100 text-green-800' 
                  : source.status === 'processing'
                  ? 'bg-yellow-100 text-yellow-800'
                  : 'bg-gray-100 text-gray-800'
              }`}>
                {source.status}
              </span>
            )}
          </div>

          <h3 className="font-medium text-gray-900 mb-1 line-clamp-2">
            {source.title || 'Untitled Source'}
          </h3>

          {source.full_text && (
            <p className="text-sm text-gray-600 mb-3 line-clamp-3">
              {truncateText(source.full_text, 150)}
            </p>
          )}

          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>Added {formatRelativeTime(source.created)}</span>
            {source.embedded_chunks && source.embedded_chunks > 0 && (
              <span>{source.embedded_chunks} chunks embedded</span>
            )}
          </div>

          {source.insights && source.insights.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <p className="text-xs text-gray-500 mb-2">
                {source.insights.length} insight{source.insights.length !== 1 ? 's' : ''}
              </p>
              <div className="space-y-1">
                {source.insights.slice(0, 2).map((insight, index) => (
                  <div key={index} className="text-xs text-gray-600 bg-gray-50 rounded p-2">
                    <div className="font-medium">{insight.title || 'Insight'}</div>
                    {insight.content && (
                      <div className="mt-1">{truncateText(insight.content, 100)}</div>
                    )}
                  </div>
                ))}
                {source.insights.length > 2 && (
                  <p className="text-xs text-gray-500">
                    +{source.insights.length - 2} more insights
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        <Menu as="div" className="relative ml-3">
          <Menu.Button className="p-1 rounded-md hover:bg-gray-100 transition-colors">
            <MoreHorizontal className="h-4 w-4 text-gray-500" />
          </Menu.Button>

          <Menu.Items className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none z-10">
            <div className="py-1">
              {sourceUrl && (
                <Menu.Item>
                  {({ active }) => (
                    <a
                      href={sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`${
                        active ? 'bg-gray-100' : ''
                      } flex items-center px-4 py-2 text-sm text-gray-700`}
                    >
                      <ExternalLink className="h-4 w-4 mr-3" />
                      Open Source
                    </a>
                  )}
                </Menu.Item>
              )}

              <Menu.Item>
                {({ active }) => (
                  <button
                    onClick={handleDelete}
                    className={`${
                      active ? 'bg-red-50' : ''
                    } flex items-center w-full px-4 py-2 text-sm text-red-700`}
                  >
                    <Trash2 className="h-4 w-4 mr-3" />
                    Delete
                  </button>
                )}
              </Menu.Item>
            </div>
          </Menu.Items>
        </Menu>
      </div>
    </div>
  );
}