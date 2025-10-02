import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi, type ChatSession, type ChatMessage } from '../lib/api';
import { toast } from 'react-hot-toast';

export function useChatSessions(notebookId: string) {
  return useQuery({
    queryKey: ['chat-sessions', notebookId],
    queryFn: async () => {
      const response = await chatApi.listSessions(notebookId);
      return response.data;
    },
    enabled: !!notebookId,
  });
}

export function useChatSession(sessionId: string) {
  return useQuery({
    queryKey: ['chat-session', sessionId],
    queryFn: async () => {
      const response = await chatApi.getSession(sessionId);
      return response.data;
    },
    enabled: !!sessionId,
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({
      notebookId,
      sessionId,
      message,
      context,
      sessionName,
    }: {
      notebookId: string;
      sessionId?: string;
      message: string;
      context?: any;
      sessionName?: string;
    }) => {
      const response = await chatApi.sendMessage(
        notebookId,
        {
          message,
          context,
          session_name: sessionName,
        },
        sessionId
      );
      return response.data;
    },
    onSuccess: (newMessage, variables) => {
      // Invalidate chat sessions to refresh the list
      queryClient.invalidateQueries({ queryKey: ['chat-sessions', variables.notebookId] });
      
      // If we have a session ID, invalidate that specific session
      if (variables.sessionId) {
        queryClient.invalidateQueries({ queryKey: ['chat-session', variables.sessionId] });
      }
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to send message';
      toast.error(message);
    },
  });
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (sessionId: string) => {
      await chatApi.deleteSession(sessionId);
      return sessionId;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      toast.success('Chat session deleted successfully!');
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Failed to delete chat session';
      toast.error(message);
    },
  });
}