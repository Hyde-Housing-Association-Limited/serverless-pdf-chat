export interface Document {
  documentid: string;
  userid: string;
  filename: string;
  filesize: string;
  docstatus: string;
  created: string;
  pages: string;
  embed_model: string;
  conversations: {
    conversationid: string;
    created: string;
    model: string
  }[];
}

export interface Conversation {
  conversationid: string;
  document: Document;
  embed_model: string;
  llm_model: string;
  messages: {
    type: string;
    data: {
      content: string;
      example: boolean;
      additional_kwargs: {};
    };
  }[];
}
