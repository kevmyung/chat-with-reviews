import streamlit as st
import random
from typing import Dict, Tuple, List, Union
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import StreamlitChatMessageHistory

from libs.config import load_model_config
from libs.models import ChatModel
from libs.chat_utils import StreamHandler, display_chat_messages, langchain_messages_format
from libs.file_utils import process_uploaded_files

region_name = 'us-east-1'
st.set_page_config(page_title='Amazon Bedrock 챗봇', page_icon="🤖", layout="wide")
st.title("🤖 Bedrock AI 리뷰 분석 챗봇")

INIT_MESSAGE = {
    "role": "assistant",
    "content": "안녕하세요! 저는 Bedrock AI 기반 리뷰 분석 챗봇입니다. 무엇을 도와드릴까요?",
}

CLAUDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        MessagesPlaceholder(variable_name="history"),
        MessagesPlaceholder(variable_name="input"),
    ]
)

def generate_response(conversation: ConversationChain, input: Union[str, List[dict]]) -> str:
    return conversation.invoke(
        {"input": input}, {"callbacks": [StreamHandler(st.empty())]}
    )

def define_system_prompt():
    radio_option = st.radio("Choose an option:", ["Summarize", "Analyze", "Recommend"])

    if radio_option == "Summarize":
        system_prompt = """Provide a summary of the reviews in a natural, conversational style within 3 sentences, as if it were a user review without annotation. 
        Please avoid listing features, and instead, integrate the key selling points naturally into the narrative."""
    elif radio_option == "Analyze":
        system_prompt = """Analyze the pros and cons of the product based on the reviews, and present them in bullet points.
        Also identify the sentiment of the given reviews by identifying the positive and negative keywords used. 
        Calculate and present the ratio of positive to negative keywords. Answer in Korean."""
    elif radio_option == "Recommend":
        system_prompt = """Extract the typical 'Time', 'Place', 'Occasion', and 'Recommended for' when the product is used or consumed.
        Please extract the most diverse set of high-frequency keywords from the text
        Answer in Korean."""
    else:
        system_prompt = ""

    return system_prompt

def render_sidebar() -> Tuple[Dict, Dict, List[st.runtime.uploaded_file_manager.UploadedFile]]:
    with st.sidebar:
        model_config = load_model_config()
        model_name_select = st.selectbox(
            '채팅 모델 💬',
            list(model_config["models"].keys()),
            key=f"{st.session_state['widget_key']}_Model_Id",
        )
        st.session_state["model_name"] = model_name_select
        model_info = model_config["models"][model_name_select]
        model_info["region_name"] = region_name

        model_kwargs = {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 200,
            "max_tokens": 100000,
            "system": define_system_prompt()
        }

        if "file_uploader_key" not in st.session_state:
            st.session_state["file_uploader_key"] = 0

        image_upload_disabled = model_info.get("image_upload_disabled", False)
        uploaded_files = st.file_uploader(
            "파일을 선택해주세요 📎",
            type=["jpg", "jpeg", "png", "txt", "pdf", "csv", "py"],
            accept_multiple_files=True,
            key=st.session_state["file_uploader_key"],
            disabled=image_upload_disabled,
        )

    return model_info, model_kwargs, uploaded_files

def main() -> None:
    if "widget_key" not in st.session_state:
        st.session_state["widget_key"] = str(random.randint(1, 1000000))

    model_info, model_kwargs, uploaded_files = render_sidebar()

    chat_model = ChatModel(st.session_state["model_name"], model_info, model_kwargs)
    conv_chain = ConversationChain(
        llm=chat_model.llm,
        verbose=True,
        memory=ConversationBufferWindowMemory(k=10, ai_prefix="Assistant",
            chat_memory=StreamlitChatMessageHistory(),
            return_messages=True,
        ),
        prompt=CLAUDE_PROMPT,
    )

    if "messages" not in st.session_state:
        st.session_state.messages = [INIT_MESSAGE]

    # Display message history
    display_chat_messages(uploaded_files)

    # User chat
    prompt = st.chat_input()

    # Images already processed
    message_images_list = [
        image_id
        for message in st.session_state.messages
        if message["role"] == "user"
        and "images" in message
        and message["images"]
        for image_id in message["images"]
    ]

    uploaded_file_ids = []
    if uploaded_files and len(message_images_list) < len(uploaded_files):
        with st.chat_message("user"):
            content_files = process_uploaded_files(
                uploaded_files, message_images_list, uploaded_file_ids
            )

            if prompt:
                context_text = ""
                context_image = []
                for content_file in content_files:
                    if content_file['type'] == 'text':
                        context_text += content_file['text'] + "\n\n"
                    else:
                        context_image.append(content_file)

                if context_text != "":
                    prompt_new = f"Here is some context for you: \n<context>\n{context_text}</context>\n\n{prompt}"
                else:
                    prompt_new = prompt

                formatted_prompt = chat_model.format_prompt(prompt_new) + context_image
                st.session_state.messages.append(
                    {"role": "user", "content": formatted_prompt, "images": uploaded_file_ids}
                )
                st.markdown(prompt)

    elif prompt:
        formatted_prompt = chat_model.format_prompt(prompt)
        st.session_state.messages.append({"role": "user", "content": formatted_prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

    st.session_state["langchain_messages"] = langchain_messages_format(
        st.session_state["langchain_messages"]
    )

    if st.session_state.messages[-1]["role"] != "assistant":
        with st.chat_message("assistant"):
            response = generate_response(
                conv_chain, [{"role": "user", "content": formatted_prompt}]
            )
        message = {"role": "assistant", "content": response}
        st.session_state.messages.append(message)

if __name__ == "__main__":
    main()