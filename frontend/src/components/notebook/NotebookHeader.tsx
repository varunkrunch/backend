import React, { useState } from 'react';
import { 
  MoreHorizontal, 
  Edit2, 
  Archive, 
  Trash2, 
  ArchiveRestore,
  Share2,
  Download
} from 'lucide-react';
import { Menu } from '@headlessui/react';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';
import { useUpdateNotebook, useDeleteNotebook, useArchiveNotebook } from '../../hooks/useNotebooks';
import { formatRelativeTime } from '../../lib/utils';
import type { Notebook } from '../../lib/api';

interface NotebookHeaderProps {
  notebook: Notebook;
}

export function NotebookHeader({ notebook }: NotebookHeaderProps) {
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    name: notebook.name,
    description: notebook.description || '',
  });

  const updateNotebook = useUpdateNotebook();
  const deleteNotebook = useDeleteNotebook();
  const archiveNotebook = useArchiveNotebook();

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: editForm,
    });
    setIsEditModalOpen(false);
  };

  const handleDelete = async () => {
    await deleteNotebook.mutateAsync(notebook.id);
    setIsDeleteModalOpen(false);
  };

  const handleArchive = async () => {
    await archiveNotebook.mutateAsync({
      id: notebook.id,
      archive: !notebook.archived,
    });
  };

  return (
    <>
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 truncate">
                {notebook.name}
              </h1>
              {notebook.archived && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                  Archived
                </span>
              )}
            </div>
            {notebook.description && (
              <p className="mt-1 text-sm text-gray-500 truncate">
                {notebook.description}
              </p>
            )}
            <p className="mt-1 text-xs text-gray-400">
              Updated {formatRelativeTime(notebook.updated)}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm">
              <Share2 className="h-4 w-4 mr-2" />
              Share
            </Button>

            <Menu as="div" className="relative">
              <Menu.Button as={Button} variant="ghost" size="sm">
                <MoreHorizontal className="h-4 w-4" />
              </Menu.Button>

              <Menu.Items className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none z-10">
                <div className="py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        onClick={() => setIsEditModalOpen(true)}
                        className={`${
                          active ? 'bg-gray-100' : ''
                        } flex items-center w-full px-4 py-2 text-sm text-gray-700`}
                      >
                        <Edit2 className="h-4 w-4 mr-3" />
                        Edit
                      </button>
                    )}
                  </Menu.Item>

                  <Menu.Item>
                    {({ active }) => (
                      <button
                        onClick={handleArchive}
                        className={`${
                          active ? 'bg-gray-100' : ''
                        } flex items-center w-full px-4 py-2 text-sm text-gray-700`}
                      >
                        {notebook.archived ? (
                          <>
                            <ArchiveRestore className="h-4 w-4 mr-3" />
                            Unarchive
                          </>
                        ) : (
                          <>
                            <Archive className="h-4 w-4 mr-3" />
                            Archive
                          </>
                        )}
                      </button>
                    )}
                  </Menu.Item>

                  <Menu.Item>
                    {({ active }) => (
                      <button
                        className={`${
                          active ? 'bg-gray-100' : ''
                        } flex items-center w-full px-4 py-2 text-sm text-gray-700`}
                      >
                        <Download className="h-4 w-4 mr-3" />
                        Export
                      </button>
                    )}
                  </Menu.Item>

                  <div className="border-t border-gray-100 my-1" />

                  <Menu.Item>
                    {({ active }) => (
                      <button
                        onClick={() => setIsDeleteModalOpen(true)}
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
      </div>

      {/* Edit Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="Edit Notebook"
      >
        <form onSubmit={handleEdit} className="space-y-4">
          <Input
            label="Name"
            value={editForm.name}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            required
          />
          <Input
            label="Description"
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
          />
          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsEditModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={updateNotebook.isPending}>
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title="Delete Notebook"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Are you sure you want to delete "{notebook.name}"? This action cannot be undone.
            All sources, notes, and chat sessions in this notebook will be permanently deleted.
          </p>
          <div className="flex justify-end gap-3">
            <Button
              variant="secondary"
              onClick={() => setIsDeleteModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDelete}
              loading={deleteNotebook.isPending}
            >
              Delete Notebook
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}