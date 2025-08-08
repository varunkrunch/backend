import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sourceApi, type Source } from '../lib/api';
import { toast } from 'react-hot-toast';

export function useSources(notebookId: string) {
  return useQuery({
    queryKey: ['sources', notebookId],
    queryFn: async () => {
      const response = await sourceApi.list(notebookId);
      return response.data;
    },
    enabled: !!notebookId,
  });
}

export function useSourcesByName(notebookName: string) {
  return useQuery({
    queryKey: ['sources', 'by-name', notebookName],
    queryFn: async () => {
      const response = await sourceApi.listByName(notebookName);
      return response.data;
    },
    enabled: !!notebookName,
  });
}

export function useSource(id: string) {
  return useQuery({
    queryKey: ['source', id],
    queryFn: async () => {
      const response = await sourceApi.get(id);
      return response.data;
    },
    enabled: !!id,
  });
}

export function useCreateSource() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ 
      notebookId, 
      notebookName, 
      data 
    }: { 
      notebookId?: string; 
      notebookName?: string; 
      data: FormData 
    }) => {
      if (notebookId) {
        const response = await sourceApi.create(notebookId, data);
        return response.data;
      } else if (notebookName) {
        const response = await sourceApi.createByName(notebookName, data);
        return response.data;
      } else {
        throw new Error('Either notebookId or notebookName must be provided');
      }
    },
    onSuccess: (newSource, variables) => {
      // Invalidate relevant queries
      if (variables.notebookId) {
        queryClient.invalidateQueries({ queryKey: ['sources', variables.notebookId] });
        queryClient.invalidateQueries({ queryKey: ['notebook', variables.notebookId] });
      }
      if (variables.notebookName) {
        queryClient.invalidateQueries({ queryKey: ['sources', 'by-name', variables.notebookName] });
        queryClient.invalidateQueries({ queryKey: ['notebook', 'by-name', variables.notebookName] });
      }
      toast.success(`Source "${newSource.title}" added successfully!`);
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to add source';
      toast.error(message);
    },
  });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (id: string) => {
      await sourceApi.delete(id);
      return id;
    },
    onSuccess: () => {
      // Invalidate all source-related queries
      queryClient.invalidateQueries({ queryKey: ['sources'] });
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      toast.success('Source deleted successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to delete source';
      toast.error(message);
    },
  });
}