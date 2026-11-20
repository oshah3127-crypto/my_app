import os
import streamlit as st
st.title("Salman FarmHouse")
st.header("Welcome")
name= st.text_input("Enter your name")
Age= st.number_input("Enter your age",min_value=18,max_value=100)
st.write(f"{name} your age is {Age}")
Gender=st.selectbox("Select your gender",["Male","Female","Karan johar"])
st.multiselect("Select your animal",["jackline","horse","kat"])
login= st.button("login")
if login:
    st.success("Form submitted successfully")
    st.write(f" your name is {name}")
    st.write(f"Your age is {Age}")
    st.write(f"Your gender is {Gender}")
    st.divider()
#st.image(r"D:\odu\videos\owais data\warwan pics n videous\nature.jpg")
st.image(os.path.join(os.getcwd(),"static","oppenheimer.jpg"))