import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notebookApi, type Notebook } from '../lib/api';
import { toast } from 'react-hot-toast';

export function useNotebooks() {
  return useQuery({
    queryKey: ['notebooks'],
    queryFn: async () => {
      const response = await notebookApi.list();
      return response.data;
    },
  });
}

export function useNotebook(id: string) {
  return useQuery({
    queryKey: ['notebook', id],
    queryFn: async () => {
      const response = await notebookApi.get(id);
      return response.data;
    },
    enabled: !!id,
  });
}

export function useNotebookByName(name: string) {
  return useQuery({
    queryKey: ['notebook', 'by-name', name],
    queryFn: async () => {
      const response = await notebookApi.getByName(name);
      return response.data;
    },
    enabled: !!name,
  });
}

export function useCreateNotebook() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (data: { name: string; description?: string }) => {
      const response = await notebookApi.create(data);
      return response.data;
    },
    onSuccess: (newNotebook) => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      toast.success(`Notebook "${newNotebook.name}" created successfully!`);
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to create notebook';
      toast.error(message);
    },
  });
}

export function useUpdateNotebook() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<Notebook> }) => {
      const response = await notebookApi.update(id, data);
      return response.data;
    },
    onSuccess: (updatedNotebook) => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      queryClient.invalidateQueries({ queryKey: ['notebook', updatedNotebook.id] });
      toast.success('Notebook updated successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to update notebook';
      toast.error(message);
    },
  });
}

export function useDeleteNotebook() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (id: string) => {
      await notebookApi.delete(id);
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      toast.success('Notebook deleted successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to delete notebook';
      toast.error(message);
    },
  });
}

export function useArchiveNotebook() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ id, archive }: { id: string; archive: boolean }) => {
      if (archive) {
        await notebookApi.archive(id);
      } else {
        await notebookApi.unarchive(id);
      }
      return { id, archive };
    },
    onSuccess: ({ archive }) => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      toast.success(`Notebook ${archive ? 'archived' : 'unarchived'} successfully!`);
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to update notebook';
      toast.error(message);
    },
  });
}