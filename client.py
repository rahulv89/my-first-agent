import requests
import streamlit as st

st.title('Marketing Emails Generator')


with st.form("user_inputs_for_rag_form", clear_on_submit=False):
	st.session_state['brand_name'] = st.text_input("Your brand name here")
	st.session_state['product_name'] = st.text_input("Your product name here")
	st.session_state['product_description'] = st.text_input("Your product description here")
	st.session_state['brand_url'] = st.text_input("Optionally, you could add a website that best represents your brand")
	submit = st.form_submit_button("Submit")

if submit:
	inputcontents = {
    "brand_name": st.session_state['brand_name'],
    "product_name": st.session_state['product_name'],
    "product_description": st.session_state['product_description'],
    "brand_url": st.session_state['brand_url'],
    "article_title": "",
    "article_text": "",
    "email": "",
    "num_steps": 0,
	}

	response = requests.post(
	"http://localhost:8000/generatemail/invoke",
	json = {'input':inputcontents}
	)
	st.write(response.json()['output']['email'])
