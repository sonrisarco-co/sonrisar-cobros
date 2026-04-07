let modalAbierto = false;

function abrirModalPago() {
    document.getElementById("modal-pago").style.display = "flex";
    modalAbierto = true;
}

function cerrarModalPago() {
    document.getElementById("modal-pago").style.display = "none";
    modalAbierto = false;
}

function agregarNumero(num) {
    const input = document.getElementById("input-monto");
    input.value += num;
}

function borrarNumero() {
    const input = document.getElementById("input-monto");
    input.value = input.value.slice(0, -1);
}

function continuarCobro() {
    const monto = document.getElementById("input-monto").value;

    if (!monto || monto === "0") {
        alert("Ingresá un monto");
        return;
    }

    window.location.href = `/pagos/nuevo/?monto=${monto}`;
}

/* 🎹 SOPORTE TECLADO FÍSICO (PC) */
document.addEventListener("keydown", function (event) {
    if (!modalAbierto) return;

    // números (fila normal y numpad)
    if (event.key >= "0" && event.key <= "9") {
        agregarNumero(event.key);
        event.preventDefault();
    }

    // borrar
    if (event.key === "Backspace") {
        borrarNumero();
        event.preventDefault();
    }

    // enter = continuar
    if (event.key === "Enter") {
        continuarCobro();
        event.preventDefault();
    }
});
