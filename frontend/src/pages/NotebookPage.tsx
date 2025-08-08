import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Plus, MessageSquare, FileText, Search } from 'lucide-react';
import { useNotebookByName } from '../hooks/useNotebooks';
import { useSourcesByName } from '../hooks/useSources';
import { useChatSessions } from '../hooks/useChat';
import { NotebookHeader } from '../components/notebook/NotebookHeader';
import { SourceCard } from '../components/notebook/SourceCard';
import { AddSourceModal } from '../components/notebook/AddSourceModal';
import { ChatInterface } from '../components/chat/ChatInterface';
import { Button } from '../components/ui/Button';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';

export function NotebookPage() {
  const { name } = useParams<{ name: string }>();
  const [activeTab, setActiveTab] = useState<'sources' | 'chat' | 'notes'>('sources');
  const [isAddSourceModalOpen, setIsAddSourceModalOpen] = useState(false);

  const decodedName = decodeURIComponent(name || '');
  
  const { data: notebook, isLoading: notebookLoading, error: notebookError } = useNotebookByName(decodedName);
  const { data: sourcesData, isLoading: sourcesLoading } = useSourcesByName(decodedName);
  const { data: chatSessions, isLoading: chatLoading } = useChatSessions(notebook?.id || '');

  if (notebookLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (notebookError || !notebook) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Notebook not found</h2>
          <p className="text-gray-600">The notebook "{decodedName}" could not be found.</p>
        </div>
      </div>
    );
  }

  const sources = sourcesData?.sources || [];
  const activeChatSession = chatSessions?.[0];

  const tabs = [
    {
      id: 'sources' as const,
      label: 'Sources',
      icon: FileText,
      count: sources.length,
    },
    {
      id: 'chat' as const,
      label: 'Chat',
      icon: MessageSquare,
      count: chatSessions?.length || 0,
    },
    {
      id: 'notes' as const,
      label: 'Notes',
      icon: FileText,
      count: notebook.notes?.length || 0,
    },
  ];

  return (
    <div className="flex flex-col h-full">
      <NotebookHeader notebook={notebook} />

      {/* Tabs */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-6">
          <nav className="flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-primary-500 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                  {tab.count > 0 && (
                    <span className={`inline-flex items-center justify-center px-2 py-1 text-xs font-bold rounded-full ${
                      activeTab === tab.id
                        ? 'bg-primary-100 text-primary-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'sources' && (
          <div className="h-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-gray-900">
                Sources ({sources.length})
              </h2>
              <Button onClick={() => setIsAddSourceModalOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Add Source
              </Button>
            </div>

            {sourcesLoading ? (
              <div className="flex items-center justify-center h-64">
                <LoadingSpinner />
              </div>
            ) : sources.length === 0 ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-center">
                  <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No sources yet</h3>
                  <p className="text-gray-600 mb-4">
                    Add your first source to get started with this notebook.
                  </p>
                  <Button onClick={() => setIsAddSourceModalOpen(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add Source
                  </Button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sources.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="h-full">
            {chatLoading ? (
              <div className="flex items-center justify-center h-full">
                <LoadingSpinner />
              </div>
            ) : (
              <ChatInterface
                notebookId={notebook.id}
                sessionId={activeChatSession?.id}
                messages={activeChatSession?.messages || []}
              />
            )}
          </div>
        )}

        {activeTab === 'notes' && (
          <div className="h-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-gray-900">
                Notes ({notebook.notes?.length || 0})
              </h2>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Add Note
              </Button>
            </div>

            {notebook.notes?.length === 0 ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-center">
                  <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No notes yet</h3>
                  <p className="text-gray-600 mb-4">
                    Create your first note to capture insights and ideas.
                  </p>
                  <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Add Note
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {notebook.notes?.map((note) => (
                  <div key={note.id} className="card p-4">
                    <h3 className="font-medium text-gray-900 mb-2">
                      {note.title || 'Untitled Note'}
                    </h3>
                    {note.content && (
                      <p className="text-gray-600 text-sm">{note.content}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <AddSourceModal
        isOpen={isAddSourceModalOpen}
        onClose={() => setIsAddSourceModalOpen(false)}
        notebookName={decodedName}
      />
    </div>
  );
}