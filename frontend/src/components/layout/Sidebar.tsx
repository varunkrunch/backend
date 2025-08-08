import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  BookOpen, 
  MessageSquare, 
  Search, 
  Settings, 
  Plus,
  Archive,
  FileText,
  Brain
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useNotebooks } from '../../hooks/useNotebooks';
import { Button } from '../ui/Button';

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const navigate = useNavigate();
  const { data: notebooks, isLoading } = useNotebooks();

  const activeNotebooks = notebooks?.filter(nb => !nb.archived) || [];
  const archivedNotebooks = notebooks?.filter(nb => nb.archived) || [];

  return (
    <div className={cn('flex flex-col h-full bg-white border-r border-gray-200', className)}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center gap-2 mb-4">
          <Brain className="h-6 w-6 text-primary-600" />
          <h1 className="text-lg font-semibold text-gray-900">Open Notebook</h1>
        </div>
        
        <Button
          onClick={() => navigate('/notebooks/new')}
          className="w-full"
          size="sm"
        >
          <Plus className="h-4 w-4 mr-2" />
          New Notebook
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        <NavLink
          to="/search"
          className={({ isActive }) =>
            cn('sidebar-item', isActive && 'active')
          }
        >
          <Search className="h-4 w-4" />
          Search
        </NavLink>

        {/* Active Notebooks */}
        {activeNotebooks.length > 0 && (
          <div className="mt-6">
            <h3 className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Notebooks
            </h3>
            <div className="space-y-1">
              {activeNotebooks.map((notebook) => (
                <NavLink
                  key={notebook.id}
                  to={`/notebooks/${encodeURIComponent(notebook.name)}`}
                  className={({ isActive }) =>
                    cn('sidebar-item', isActive && 'active')
                  }
                >
                  <BookOpen className="h-4 w-4" />
                  <span className="truncate">{notebook.name}</span>
                </NavLink>
              ))}
            </div>
          </div>
        )}

        {/* Archived Notebooks */}
        {archivedNotebooks.length > 0 && (
          <div className="mt-6">
            <h3 className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Archived
            </h3>
            <div className="space-y-1">
              {archivedNotebooks.map((notebook) => (
                <NavLink
                  key={notebook.id}
                  to={`/notebooks/${encodeURIComponent(notebook.name)}`}
                  className={({ isActive }) =>
                    cn('sidebar-item opacity-60', isActive && 'active')
                  }
                >
                  <Archive className="h-4 w-4" />
                  <span className="truncate">{notebook.name}</span>
                </NavLink>
              ))}
            </div>
          </div>
        )}

        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600"></div>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn('sidebar-item', isActive && 'active')
          }
        >
          <Settings className="h-4 w-4" />
          Settings
        </NavLink>
      </div>
    </div>
  );
}