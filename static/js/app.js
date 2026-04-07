function seleccionarMetodo(id, boton) {
    const input = document.getElementById("metodo-seleccionado");
    input.value = id;

    document.querySelectorAll(".metodo-btn").forEach(btn => {
        btn.classList.remove("activo");
    });

    boton.classList.add("activo");
}
