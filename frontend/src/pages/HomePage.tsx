import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, BookOpen, Clock, Archive } from 'lucide-react';
import { useNotebooks } from '../hooks/useNotebooks';
import { Button } from '../components/ui/Button';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { formatRelativeTime } from '../lib/utils';

export function HomePage() {
  const navigate = useNavigate();
  const { data: notebooks, isLoading } = useNotebooks();

  const activeNotebooks = notebooks?.filter(nb => !nb.archived) || [];
  const recentNotebooks = activeNotebooks
    .sort((a, b) => new Date(b.updated).getTime() - new Date(a.updated).getTime())
    .slice(0, 6);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Welcome to Open Notebook
          </h1>
          <p className="text-lg text-gray-600">
            Your AI-powered research and knowledge management platform
          </p>
        </div>

        {/* Quick Actions */}
        <div className="mb-8">
          <div className="flex items-center gap-4">
            <Button
              onClick={() => navigate('/notebooks/new')}
              size="lg"
            >
              <Plus className="h-5 w-5 mr-2" />
              Create New Notebook
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigate('/search')}
              size="lg"
            >
              Search All Content
            </Button>
          </div>
        </div>

        {/* Recent Notebooks */}
        {recentNotebooks.length > 0 ? (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Recent Notebooks</h2>
              <Button
                variant="ghost"
                onClick={() => navigate('/notebooks')}
              >
                View All
              </Button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {recentNotebooks.map((notebook) => (
                <div
                  key={notebook.id}
                  onClick={() => navigate(`/notebooks/${encodeURIComponent(notebook.name)}`)}
                  className="card p-6 hover:shadow-md transition-shadow cursor-pointer"
                >
                  <div className="flex items-start justify-between mb-3">
                    <BookOpen className="h-6 w-6 text-primary-600 flex-shrink-0" />
                    {notebook.archived && (
                      <Archive className="h-4 w-4 text-gray-400" />
                    )}
                  </div>
                  
                  <h3 className="font-semibold text-gray-900 mb-2 line-clamp-2">
                    {notebook.name}
                  </h3>
                  
                  {notebook.description && (
                    <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                      {notebook.description}
                    </p>
                  )}
                  
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatRelativeTime(notebook.updated)}
                    </div>
                    <div className="flex items-center gap-3">
                      {notebook.sources && notebook.sources.length > 0 && (
                        <span>{notebook.sources.length} sources</span>
                      )}
                      {notebook.notes && notebook.notes.length > 0 && (
                        <span>{notebook.notes.length} notes</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center py-12">
            <BookOpen className="h-16 w-16 text-gray-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              No notebooks yet
            </h2>
            <p className="text-gray-600 mb-6 max-w-md mx-auto">
              Create your first notebook to start organizing your research, sources, and insights.
            </p>
            <Button
              onClick={() => navigate('/notebooks/new')}
              size="lg"
            >
              <Plus className="h-5 w-5 mr-2" />
              Create Your First Notebook
            </Button>
          </div>
        )}

        {/* Stats */}
        {notebooks && notebooks.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="card p-6 text-center">
              <div className="text-2xl font-bold text-primary-600 mb-1">
                {activeNotebooks.length}
              </div>
              <div className="text-sm text-gray-600">Active Notebooks</div>
            </div>
            
            <div className="card p-6 text-center">
              <div className="text-2xl font-bold text-green-600 mb-1">
                {notebooks.reduce((acc, nb) => acc + (nb.sources?.length || 0), 0)}
              </div>
              <div className="text-sm text-gray-600">Total Sources</div>
            </div>
            
            <div className="card p-6 text-center">
              <div className="text-2xl font-bold text-blue-600 mb-1">
                {notebooks.reduce((acc, nb) => acc + (nb.notes?.length || 0), 0)}
              </div>
              <div className="text-sm text-gray-600">Total Notes</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}