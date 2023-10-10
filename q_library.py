import torch
import inspect
# import circuit

# ---
# DEFINITION OF MATRICES
# Defining the gates for a single qubit i.e. the most simple form
# - stack instead of tensor to make forward differentiable
# - around 3 million calls for 100 epochs
# ---

sqrt_of_two = torch.sqrt(torch.tensor(2, dtype=torch.complex128))   # saving computation by pre calculating
hadamard_single = torch.tensor([[1, 1], [1, -1]], dtype=torch.complex128) / sqrt_of_two


def ry_matrix(angle):
    cos_half_angle = torch.cos(angle*0.5)
    sin_half_angle = torch.sin(angle*0.5)

    line1 = torch.stack((cos_half_angle, -sin_half_angle))
    line2 = torch.stack((sin_half_angle, cos_half_angle))

    ry_mat = torch.stack((line1, line2)).type(torch.complex128)

    return ry_mat

def ry_matrix_t(angle):
    return torch.conj(ry_matrix(angle)).t()


def rz_matrix(angle):
    neg_exp = torch.exp(-0.5j*angle)
    pos_exp = torch.exp(0.5j*angle)
    zero_int = torch.tensor(0)

    line1 = torch.stack((neg_exp, zero_int))
    line2 = torch.stack((zero_int, pos_exp))

    rz_mat = torch.stack((line1, line2)).type(torch.complex128)

    return rz_mat

def rz_matrix_t(angle):
    return torch.conj(rz_matrix(angle)).t()


# The Controlled RZ Matrix
# returns the matrix for rz on certain qubit q and a control on q - 1
# CONDITION: q - c must be one. Differentiable Function
def crz_matrix(q, num_q, angle):
    dim = 2 ** num_q
    per_length = 2 ** q * 2  # how long is an interval
    num_rep = 2 ** (q - 1)  # how often is a value repeated
    help_diag = torch.ones(per_length, dtype=torch.complex128)
    for k in range(num_rep):
        help_diag[num_rep + k] = rz_matrix(angle)[0][0]
        help_diag[num_rep + k + per_length // 2] = rz_matrix(angle)[1][1]
    final_diag = help_diag
    # join the intervals in dimension length
    for _ in range(dim // per_length - 1):
        final_diag = torch.cat((final_diag, help_diag))
    # crz = torch.from_numpy(final_diag).type(torch.complex64)
    crz = torch.diag(final_diag)
    return crz

def close_ring(num_q, angle):
    dim = 2 ** num_q
    values = torch.tensor([rz_matrix(angle)[0][0], rz_matrix(angle)[1][1]], requires_grad=True)
    help_diag = torch.ones(dim // 2, dtype=torch.complex128, requires_grad=True)  # first half only ones for control
    help_diag = torch.cat((help_diag, values.tile((dim // 4,))))  # The second half is alternately filled with - +
    close_matrix = torch.diag(help_diag)
    return close_matrix


# ---
# DEFINITION OF LAYERS
#  composing of the simple matrices to build same-type-gate parallel layers or rings in the size of the given number of quantum's of the circuit
#  adjacent function always apart since conditions in function break the computation graph

# for the rz layers: In case len(angles) > qubits (number of features > number of qubits) the order is for ansatz: 1, 6, 4, 2, 7, 5; adjoint: 5, 7, 2, 4, 6, 1
# ---

def crz_ring(num_q, angles, state):
    for i in range(num_q - 1):
        state = torch.matmul(crz_matrix(i + 1, num_q, angles[i]), state)
    state = torch.matmul(close_ring(num_q, angles[-1]), state)
    return state

def adj_crz_ring(num_q, angles, state):
    state = torch.matmul(torch.conj(close_ring(num_q, angles[-1]).t()), state)
    for i in range(num_q - 1, 0, -1):  # backwards
        state = torch.matmul(torch.conj(crz_matrix(i, num_q, angles[i-1])).t(), state)
    return state


def ry_layer(num_q, angles, state):
    ry = ry_matrix(angles[-1])
    for i in range(num_q - 1):
        ry = torch.kron(ry, ry_matrix(angles[(num_q - 1 - (i+1))]))
    state = torch.matmul(ry, state)
    return state

def adj_ry_layer(num_q, angles, state):
    ry = ry_matrix_t(angles[-1])
    for i in range(num_q - 1):
        ry = torch.kron(ry, ry_matrix_t(angles[(num_q - 1 - (i+1))]))
    state = torch.matmul(ry, state)
    return state


def rz_layer(num_q, angles, state, start):
    rz = rz_matrix(angles[start % len(angles)])
    for _ in range(num_q - 1):
        start += 1
        rz = torch.kron(rz, rz_matrix(angles[start % len(angles)]))
    state = torch.matmul(rz, state)
    return state

def adj_rz_layer(num_q, angles, state, start):
    rz = rz_matrix_t(angles[start % len(angles)])
    for _ in range(num_q - 1):
        start += 1
        rz = torch.kron(rz, rz_matrix_t(angles[start % len(angles)]))
    state = torch.matmul(rz, state)
    return state


def h_layer(num_q, state):
    h = hadamard_single
    for _ in range(num_q - 1):
        h = torch.kron(h, hadamard_single)
    return torch.matmul(h, state)


# ------------
#
# def count_and_record_layer_calls(func):
#     # Use the inspect module to get the source code of the function
#     source_code = inspect.getsource(func)
#
#     # Define the specific layer function names you want to track
#     layer_functions = ['h_layer', 'rz_layer', 'ry_layer', 'crz_ring']
#
#     # Split the source code into lines
#     lines = source_code.split('\n')
#
#     # Initialize dictionaries to store the count and positions of layer function calls
#     layer_count = {layer: 0 for layer in layer_functions}
#     layer_positions = {layer: [] for layer in layer_functions}
#
#     # Iterate through the lines and look for specific layer function calls
#     for i, line in enumerate(lines, start=1):
#         for layer_function in layer_functions:
#             if f'{layer_function}(' in line:
#                 # Increment the count for the layer function
#                 layer_count[layer_function] += 1
#
#                 # Record the position of the layer function call
#                 layer_positions[layer_function].append(i)
#
#     return layer_count, layer_positions
#
# # def adj_generator(circuit):
# #
# #
#
# def generate_adjusted_block(func):
#     # Use the inspect module to get the source code of the function
#     source_code = inspect.getsource(func)
#
#     # Define the specific layer function names and their corresponding adjustments
#     layer_functions = {
#         'h_layer': 'h_layer',
#         'rz_layer': 'adj_rz_layer',
#         'ry_layer': 'adj_ry_layer',
#         'crz_ring': 'adj_crz_ring',
#     }
#
#     # Split the source code into lines
#     lines = source_code.split('\n')
#
#     # Initialize a list to store the adjusted code
#     adjusted_code = []
#
#     # Iterate through the lines and look for specific layer function calls
#     for line in lines:
#         for layer_function, adjustment_function in layer_functions.items():
#             if f'{layer_function}(' in line:
#                 # Replace the original layer function with the corresponding adjustment function
#                 line = line.replace(layer_function, adjustment_function)
#         adjusted_code.append(line)
#
#     # Combine the adjusted code lines into a single string
#     adjusted_code_str = '\n'.join(adjusted_code)
#
#     # Define a new function with the adjusted code
#     namespace = {}
#     exec(adjusted_code_str, namespace)
#     adjusted_block = namespace[func.__name__]
#
#     return adjusted_block
#
#
# # Define your function
# def block(num_q, x, block_params, start, state):
#     state = h_layer(num_q, state)
#     state = rz_layer(num_q, x, state, start)
#     state = ry_layer(num_q, block_params[0], state)
#     state = crz_ring(num_q, block_params[1], state)
#     state = h_layer(num_q, state)  # Additional h_layer call
#     return state
#
# #
# # # Get the count and positions of specific layer function calls within the 'block' function
# # layer_count, layer_positions = count_and_record_layer_calls(block)
# #
# # # Print the count and positions of each layer function
# # for layer_function, count in layer_count.items():
# #     print(f'{layer_function}: Count = {count}')
# #     print(f'{layer_function}: Positions = {layer_positions[layer_function]}')
# #
#
#
# # Generate the adjusted function
# adjusted_block = generate_adjusted_block(block)
#
#
# def initial_state(n_qubits):
#     return torch.tensor([1] + [0] * (2 ** n_qubits - 1), dtype=torch.complex128, requires_grad=True)
#
#
# print(adjusted_block(5, [0,1], 2 * torch.pi * torch.rand(5, 2, 5), 0, initial_state(5)))
